import asyncio
import os
import secrets
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .database import get_db
from .engine_runner import EngineRunError, run_engine
from .mock_engine import season_history, today_recommendation

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


def _engine_explanation(result: dict) -> str:
    moisture_pct = float(result.get("soil_moisture", 0) or 0) * 100
    if result.get("severe_stress"):
        return (
            f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : stress "
            "hydrique sévère détecté, arrosage recommandé sans délai."
        )
    if result.get("should_irrigate"):
        duration_min = round((result.get("duration_s", 0) or 0) / 60)
        volume = float(result.get("volume", 0) or 0)
        return (
            f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : un "
            f"arrosage de {duration_min} min ({volume:.0f} L) est recommandé aujourd'hui."
        )
    return f"Humidité du sol à {moisture_pct:.0f}% (moteur physique) : pas d'arrosage nécessaire aujourd'hui."


def _job_result_to_recommendation(job: models.RecommendationJobModel) -> dict:
    result = job.result
    # The engine reports soil moisture as a volumetric fraction (theta,
    # typically 0-0.5) and duration in seconds; the API/app contract expects
    # a 0-100 percent and minutes. Straight unit conversion, not a change to
    # the physical model.
    return {
        "date": job.finished_at.date().isoformat(),
        "should_irrigate": bool(result.get("should_irrigate", False)),
        "duration_minutes": round((result.get("duration_s", 0) or 0) / 60),
        "volume_liters": round(float(result.get("volume", 0) or 0), 1),
        "severe_stress_alert": bool(result.get("severe_stress", False)),
        "soil_moisture_percent": round(float(result.get("soil_moisture", 0) or 0) * 100, 1),
        "explanation": _engine_explanation(result),
    }


def _current_recommendation(field_id: str, db: Session) -> dict:
    """Prefers the latest completed real-engine run for this field; falls
    back to the deterministic mock only if the engine has never completed
    successfully for it yet."""
    job = _latest_done_job(field_id, db)
    if job is not None and job.result is not None:
        return _job_result_to_recommendation(job)
    return today_recommendation(field_id, date.today())


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
    field.size_hectares = payload.size_hectares
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
    return _current_recommendation(field_id, db)


@app.get("/fields/{field_id}/history", response_model=list[schemas.HistoryPointOut])
def get_history(
    field_id: str,
    current_user: models.UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    field = _field_or_404(field_id, db)
    _require_field_access(field, current_user)

    mock_points = season_history(field_id, date.today())

    # Overlay any day where the real engine actually completed a run for
    # this field on top of the mock series, so days that were genuinely
    # computed stop showing fabricated numbers.
    done_jobs = (
        db.query(models.RecommendationJobModel)
        .filter_by(field_id=field_id, status="done")
        .order_by(models.RecommendationJobModel.finished_at.asc())
        .all()
    )
    real_points_by_date = {}
    for job in done_jobs:
        if job.result is None or job.finished_at is None:
            continue
        reco = _job_result_to_recommendation(job)
        real_points_by_date[reco["date"]] = {
            "date": reco["date"],
            "water_used_liters": reco["volume_liters"],
            "soil_moisture_percent": reco["soil_moisture_percent"],
            "severe_stress_alert": reco["severe_stress_alert"],
        }

    return [real_points_by_date.get(point["date"], point) for point in mock_points]


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
                needs_attention=reco["severe_stress_alert"],
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


def _engine_config() -> tuple[str, str]:
    octave_cmd = os.environ.get("ENGINE_OCTAVE_CMD", "octave")
    script_path = os.environ.get("ENGINE_SCRIPT_PATH", "run_recommendation.m")
    return octave_cmd, script_path


async def _execute_job(job_id: str, field_id: str) -> None:
    from .database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(models.RecommendationJobModel).filter_by(id=job_id).first()
        field = db.query(models.FieldModel).filter_by(id=field_id).first()
        if job is None or field is None:
            return
        job.status = "running"
        db.commit()

        octave_cmd, script_path = _engine_config()
        params = {
            "culture": field.crop,
            "lat": field.latitude,
            "lon": field.longitude,
            "jour_julien": field.engine_last_julian_day or date.today().timetuple().tm_yday,
            "psi_old": field.engine_psi_state,
            "theta_infiltre": field.engine_theta_infiltre,
        }
        try:
            result = await run_engine(params, octave_cmd=octave_cmd, script_path=script_path)
        except EngineRunError as exc:
            job.status = "failed"
            job.error = exc.message
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        try:
            # The engine can return a technically-valid JSON response (exit
            # code 0) where a numeric field is nonetheless `null` — e.g. a
            # NaN from a known unresolved unit-conversion issue in
            # dailyIrrigationRecommendation.m (see its comments). Treat that
            # as a failed run instead of silently persisting a "done" job
            # with missing data — the app must never show a incomplete
            # result as if it were a real recommendation.
            missing = [
                key
                for key in ("should_irrigate", "duration_s", "volume", "soil_moisture", "severe_stress")
                if result.get(key) is None
            ]
            if missing:
                raise ValueError(f"Champs manquants dans le resultat du moteur: {', '.join(missing)}")

            job.result = {
                "should_irrigate": result["should_irrigate"],
                "duration_s": result["duration_s"],
                "volume": result["volume"],
                "soil_moisture": result["soil_moisture"],
                "severe_stress": result["severe_stress"],
            }
            field.engine_psi_state = result.get("psi_old")
            field.engine_theta_infiltre = result.get("theta_infiltre", field.engine_theta_infiltre)
            field.engine_last_julian_day = result.get("jour_julien", field.engine_last_julian_day)
            job.status = "done"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            job.status = "failed"
            job.error = f"Résultat du moteur invalide: {exc}"
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return
    finally:
        db.close()


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

    task = asyncio.create_task(_execute_job(job.id, field_id))
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
