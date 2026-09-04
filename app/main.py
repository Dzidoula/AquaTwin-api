import asyncio
import os
import secrets
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .engine_runner import SEASON_LOCK, EngineRunError, run_engine
from .jobs import build_recommendation_dict, emitter_flow_env, execute_job, execute_simulation_job

app = FastAPI(title="AquaTwin-Drip Mock API")

MOCK_OTP_CODE = "1234"

# The event loop only holds a weak reference to tasks created via
# asyncio.create_task; an un-retained task may be garbage collected before
# it completes. Since _execute_job can run for up to 30 minutes, we keep a
# strong reference here until the task finishes.
_background_tasks: set[asyncio.Task] = set()


def _role_for_phone(phone: str) -> str:
    # Mock-only convention: any phone containing "1111" logs in as a
    # cooperative agent, everything else as a farmer. There is no real
    # SMS/identity provider behind this stub.
    return "agent_cooperative" if "1111" in phone else "agriculteur"


@app.post("/auth/otp/request", status_code=200)
def request_otp(payload: schemas.OtpRequest):
    if not payload.phone.strip():
        raise HTTPException(status_code=422, detail="Numéro de téléphone requis")
    return {}


@app.post("/auth/otp/verify", response_model=schemas.UserOut)
def verify_otp(payload: schemas.OtpVerify, db: Session = Depends(get_db)):
    if payload.code != MOCK_OTP_CODE:
        raise HTTPException(status_code=401, detail="Code invalide")

    user = db.query(models.UserModel).filter_by(phone=payload.phone).first()
    if user is None:
        user = models.UserModel(phone=payload.phone, role=_role_for_phone(payload.phone))
        db.add(user)
        db.commit()
        db.refresh(user)

    # Mock-only: a real deployment would issue a signed/expiring token (e.g.
    # JWT) from an identity provider. This stub just mints a random opaque
    # string and stores it on the user row so later requests can look the
    # user up by it (see Task 2).
    user.token = secrets.token_hex(16)
    db.commit()
    db.refresh(user)
    return schemas.UserOut(id=user.id, phone=user.phone, role=user.role, token=user.token, name=user.name)


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> models.UserModel:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentification requise")
    token = authorization.removeprefix("Bearer ")
    user = db.query(models.UserModel).filter_by(token=token).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Session invalide")
    return user


@app.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.UserModel = Depends(get_current_user)):
    return schemas.UserOut(
        id=current_user.id,
        phone=current_user.phone,
        role=current_user.role,
        token=current_user.token,
        name=current_user.name,
    )


@app.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.UserUpdate,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.name = payload.name
    db.commit()
    db.refresh(current_user)
    return schemas.UserOut(
        id=current_user.id,
        phone=current_user.phone,
        role=current_user.role,
        token=current_user.token,
        name=current_user.name,
    )


def _latest_done_job(field_id: str, db: Session) -> models.RecommendationJobModel | None:
    return (
        db.query(models.RecommendationJobModel)
        .filter_by(field_id=field_id, status="done")
        .order_by(models.RecommendationJobModel.finished_at.desc())
        .first()
    )


def _job_result_to_recommendation(job: models.RecommendationJobModel) -> dict:
    return build_recommendation_dict(job.result, job.finished_at)


def _current_recommendation(field_id: str, db: Session) -> dict | None:
    """The latest completed real-engine run for this field, or None if the
    engine has never completed successfully for it yet. No fabricated
    fallback: a field with no real run has no recommendation, full stop."""
    job = _latest_done_job(field_id, db)
    if job is not None and job.result is not None:
        return _job_result_to_recommendation(job)
    return None


def _field_or_404(field_id: str, db: Session) -> models.FieldModel:
    field = db.query(models.FieldModel).filter_by(id=field_id).first()
    if field is None:
        raise HTTPException(status_code=404, detail="Champ introuvable")
    return field


def _require_field_access(field: models.FieldModel, user: models.UserModel) -> None:
    if user.role == "agent_cooperative":
        return
    if field.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Accès refusé")


@app.post("/fields", response_model=schemas.FieldOut, status_code=201)
def create_field(
    payload: schemas.FieldIn,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = models.FieldModel(
        owner_id=current_user.id,
        crop=payload.crop,
        size_hectares=payload.size_hectares,
        latitude=payload.latitude,
        longitude=payload.longitude,
        planting_date=payload.planting_date,
        soil_type=payload.soil_type,
        emitter_flow_lh=payload.emitter_flow_lh,
    )
    db.add(field)
    db.commit()
    db.refresh(field)
    return schemas.FieldOut(
        id=field.id,
        crop=field.crop,
        size_hectares=field.size_hectares,
        latitude=field.latitude,
        longitude=field.longitude,
        planting_date=field.planting_date,
        soil_type=field.soil_type,
        emitter_flow_lh=field.emitter_flow_lh,
        auto_recommend_enabled=field.auto_recommend_enabled,
    )


@app.get("/fields/mine", response_model=list[schemas.FieldOut])
def list_my_fields(
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    fields = db.query(models.FieldModel).filter_by(owner_id=current_user.id).all()
    return [
        schemas.FieldOut(
            id=f.id,
            crop=f.crop,
            size_hectares=f.size_hectares,
            latitude=f.latitude,
            longitude=f.longitude,
            planting_date=f.planting_date,
            soil_type=f.soil_type,
            emitter_flow_lh=f.emitter_flow_lh,
            auto_recommend_enabled=f.auto_recommend_enabled,
        )
        for f in fields
    ]


@app.patch("/fields/{field_id}")
def update_field(
    field_id: str,
    payload: schemas.FieldUpdate,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)
    if payload.size_hectares is not None:
        field.size_hectares = payload.size_hectares
    if payload.auto_recommend_enabled is not None:
        field.auto_recommend_enabled = payload.auto_recommend_enabled
    db.commit()
    return {}


@app.get("/fields/{field_id}/recommendation", response_model=schemas.RecommendationOut)
def get_recommendation(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)
    reco = _current_recommendation(field_id, db)
    if reco is None:
        raise HTTPException(
            status_code=404,
            detail="Aucune recommandation disponible : aucun calcul n'a encore abouti pour ce champ.",
        )
    return reco


@app.get("/fields/{field_id}/recommendation/animation", response_model=schemas.AnimationFrameOut)
def get_recommendation_animation(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Wetting-bulb animation frames for the latest completed run — fetched
    separately from GET /recommendation (~200KB, not something every screen
    load should pay for). 404 if the latest run didn't produce any (e.g.
    nothing to irrigate that day, or an older engine version)."""
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)
    job = _latest_done_job(field_id, db)
    animation = job.result.get("animation") if job is not None and job.result else None
    if not animation:
        raise HTTPException(status_code=404, detail="Pas d'animation disponible pour ce champ.")
    return animation


@app.get("/fields/{field_id}/history", response_model=list[schemas.HistoryPointOut])
def get_history(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    # Only days where the real engine actually completed a run for this
    # field — no fabricated filler for days nothing was computed.
    done_jobs = (
        db.query(models.RecommendationJobModel)
        .filter_by(field_id=field_id, status="done")
        .order_by(models.RecommendationJobModel.finished_at.asc())
        .all()
    )
    points_by_date: dict[str, dict] = {}
    for job in done_jobs:
        if job.result is None or job.finished_at is None:
            continue
        reco = _job_result_to_recommendation(job)
        points_by_date[reco["date"]] = {
            "date": reco["date"],
            "water_used_liters": reco["volume_liters"],
            "soil_moisture_percent": reco["soil_moisture_percent"],
            "severe_stress_alert": reco["severe_stress_alert"],
        }

    return [points_by_date[d] for d in sorted(points_by_date)]


@app.get("/cooperative/fields", response_model=list[schemas.FarmerFieldSummaryOut])
def list_managed_fields(
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "agent_cooperative":
        raise HTTPException(status_code=403, detail="Réservé aux agents de coopérative")
    fields = (
        db.query(models.FieldModel)
        .join(models.UserModel)
        .filter(models.UserModel.role == "agriculteur")
        .all()
    )
    summaries = []
    for field in fields:
        reco = _current_recommendation(field.id, db)
        summaries.append(
            schemas.FarmerFieldSummaryOut(
                field_id=field.id,
                farmer_name=field.owner.name or field.owner.phone,
                farmer_phone=field.owner.phone,
                crop=field.crop,
                size_hectares=field.size_hectares,
                # No fabricated alert when no real run exists yet.
                needs_attention=False if reco is None else reco["severe_stress_alert"],
            )
        )
    return summaries


@app.post("/cooperative/farmers", response_model=schemas.AssistedFarmerOut, status_code=201)
def create_assisted_farmer(
    payload: schemas.AssistedFarmerIn,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Mock-only: a real deployment would still verify the farmer's phone
    # somehow (e.g. an SMS the agent reads back to them). This mock skips
    # OTP entirely for agent-created accounts — the agent is already an
    # authenticated, trusted intermediary and may not have the farmer's
    # phone in hand during the visit.
    if current_user.role != "agent_cooperative":
        raise HTTPException(status_code=403, detail="Réservé aux agents de coopérative")

    existing = db.query(models.UserModel).filter_by(phone=payload.phone).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Un compte existe déjà pour ce numéro")

    farmer = models.UserModel(
        phone=payload.phone,
        name=payload.name,
        role="agriculteur",
        token=secrets.token_hex(16),
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return schemas.AssistedFarmerOut(id=farmer.id, phone=farmer.phone, name=farmer.name, token=farmer.token)


def _season_engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get("SEASON_SCRIPT_PATH", "run_season_prediction.m")
    return octave_cmd, script_path


def _season_data_driven_engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get(
        "SEASON_DATA_DRIVEN_SCRIPT_PATH", "run_season_prediction_data_driven.m"
    )
    return octave_cmd, script_path


def _optimal_harvest_engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get("OPTIMAL_HARVEST_SCRIPT_PATH", "run_optimal_harvest.m")
    return octave_cmd, script_path


@app.post("/fields/{field_id}/season-simulation", response_model=schemas.SeasonSimulationOut)
async def simulate_season(
    field_id: str,
    payload: schemas.SeasonSimulationIn,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    octave_cmd, script_path = _season_engine_config()
    params = {"culture": field.crop, "irrigation_coverage": payload.irrigation_coverage}
    try:
        result = await run_engine(params, octave_cmd=octave_cmd, script_path=script_path, lock=SEASON_LOCK)
    except EngineRunError as exc:
        raise HTTPException(status_code=502, detail=exc.message)

    return schemas.SeasonSimulationOut(
        points=[schemas.SeasonPointOut(**p) for p in result["points"]],
        final_rendement=result["final_rendement"],
        appreciation=result["appreciation"],
    )


@app.post(
    "/fields/{field_id}/season-simulation-data-driven",
    response_model=schemas.SeasonSimulationDataDrivenOut,
)
async def simulate_season_data_driven(
    field_id: str,
    payload: schemas.SeasonSimulationDataDrivenIn,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alex's data-driven yield model (rendementPredictionGood.m, ported to
    run under Octave as PredictSeasonYieldDataDriven.m) — a second,
    independent scenario-test model alongside the AquaCrop-FAO one behind
    /season-simulation, for comparison in the Prévisions screen."""
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    if len(payload.jours_test) != len(payload.eto_test):
        raise HTTPException(
            status_code=422, detail="jours_test et eto_test doivent avoir la meme longueur."
        )
    if not payload.jours_test:
        raise HTTPException(status_code=422, detail="Au moins un jour a tester est requis.")

    octave_cmd, script_path = _season_data_driven_engine_config()
    params = {
        "lat": field.latitude,
        "lon": field.longitude,
        "culture": field.crop,
        "date_semence": field.planting_date,
        "jours_test": payload.jours_test,
        "eto_test": payload.eto_test,
    }
    try:
        result = await run_engine(
            params,
            octave_cmd=octave_cmd,
            script_path=script_path,
            lock=SEASON_LOCK,
            timeout_s=300,
        )
    except EngineRunError as exc:
        raise HTTPException(status_code=502, detail=exc.message)

    return schemas.SeasonSimulationDataDrivenOut(
        rendement=result["rendement"],
        biomasse=result["biomasse"],
        appreciation=result["appreciation"],
    )


@app.post("/fields/{field_id}/optimal-harvest", response_model=schemas.OptimalHarvestOut)
async def find_optimal_harvest(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alex's OptimalHarvest.m, ported to run under Octave with an
    iteration cap (OptimalHarvestDataDriven.m — see its own comments: the
    original's stop condition checked for a value EvaluerRendement.m can
    never return, so it never terminated on its own, even under MATLAB).
    Searches for the best-yield irrigation strategy for the Prévisions
    screen's "meilleur rendement" feature."""
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    octave_cmd, script_path = _optimal_harvest_engine_config()
    params = {
        "lat": field.latitude,
        "lon": field.longitude,
        "culture": field.crop,
        "date_semence": field.planting_date,
    }
    try:
        result = await run_engine(
            params,
            octave_cmd=octave_cmd,
            script_path=script_path,
            lock=SEASON_LOCK,
            timeout_s=300,
        )
    except EngineRunError as exc:
        raise HTTPException(status_code=502, detail=exc.message)

    return schemas.OptimalHarvestOut(
        rendement=result["rendement"],
        optimal_eto=result["optimal_eto"],
        appreciation=result["appreciation"],
        n_iterations=result["n_iterations"],
    )


@app.post("/fields/{field_id}/recommendation/run", response_model=schemas.RunJobResponse, status_code=202)
async def run_recommendation_job(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    job = models.RecommendationJobModel(field_id=field_id, status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    task = asyncio.create_task(execute_job(job.id, field_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return schemas.RunJobResponse(job_id=job.id, status=job.status)


@app.get("/fields/{field_id}/recommendation/jobs/{job_id}", response_model=schemas.RecommendationJobOut)
def get_recommendation_job(
    field_id: str,
    job_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    job = db.query(models.RecommendationJobModel).filter_by(id=job_id, field_id=field_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Calcul introuvable")

    return schemas.RecommendationJobOut(
        id=job.id,
        field_id=job.field_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        result=job.result,
        error=job.error,
    )


@app.post("/simulations/run", response_model=schemas.RunJobResponse, status_code=202)
async def run_simulation(
    payload: schemas.SimulationRunRequest,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = models.SimulationJobModel(status="pending", user_id=current_user.id)
    db.add(job)
    db.commit()
    db.refresh(job)

    params = {
        "culture": payload.culture,
        "lat": payload.lat,
        "lon": payload.lon,
        "size_hectares": payload.size_hectares,
        "type_sol": payload.type_sol,
        "jour_julien": date.today().timetuple().tm_yday,
        "psi_old": None,
        "theta_infiltre": 0,
    }

    task = asyncio.create_task(
        execute_simulation_job(job.id, params, extra_env=emitter_flow_env(payload.emitter_flow_lh))
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return schemas.RunJobResponse(job_id=job.id, status=job.status)


@app.get("/simulations/jobs/{job_id}", response_model=schemas.SimulationJobOut)
def get_simulation_job(
    job_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.query(models.SimulationJobModel).filter_by(id=job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Simulation introuvable")

    return schemas.SimulationJobOut(
        id=job.id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        result=job.result,
        error=job.error,
    )
