from typing import Literal

from pydantic import BaseModel, Field

Crop = Literal["mais", "tomate", "coton"]

# The only 6 values TenseurSol.m actually branches on (see its `switch`) —
# not the 11-way USDA classification classifySoilType.m/ISRIC produces.
# Deliberately narrower: this is what the farmer picks, in a vocabulary
# they can select from a short list.
SoilType = Literal["sableux", "limoneux", "franco-limoneux", "argileux", "franco-argileux", "limono-argileux"]


class OtpRequest(BaseModel):
    phone: str


class OtpVerify(BaseModel):
    phone: str
    code: str


class UserOut(BaseModel):
    id: str
    phone: str
    role: str
    token: str
    name: str | None = None


class UserUpdate(BaseModel):
    name: str


class AssistedFarmerIn(BaseModel):
    phone: str
    name: str | None = None


class AssistedFarmerOut(BaseModel):
    id: str
    phone: str
    name: str | None
    token: str


class FieldIn(BaseModel):
    crop: Crop
    size_hectares: float
    latitude: float
    longitude: float
    planting_date: str
    # None ("je ne sais pas") means the engine falls back to classifySoilType
    # (ISRIC) for this field, same as if it had never been given.
    soil_type: SoilType | None = None
    # None means the engine falls back to its own hardcoded default
    # (parameterGoutteur.m) — same "null = default" spirit as soil_type.
    emitter_flow_lh: float | None = Field(default=None, gt=0)


class FieldUpdate(BaseModel):
    size_hectares: float | None = None
    auto_recommend_enabled: bool | None = None


class FieldOut(BaseModel):
    id: str
    crop: str
    size_hectares: float
    latitude: float
    longitude: float
    planting_date: str
    soil_type: SoilType | None = None
    emitter_flow_lh: float | None = None
    auto_recommend_enabled: bool = False


class RecommendationOut(BaseModel):
    date: str
    should_irrigate: bool
    duration_minutes: int
    volume_liters: float
    severe_stress_alert: bool
    soil_moisture_percent: float
    explanation: str
    # Whether this run produced wetting-bulb animation frames (see
    # GET /fields/{id}/recommendation/animation) — a flag, not the frames
    # themselves, since those run ~200KB and this endpoint is polled on
    # every screen load.
    has_animation: bool = False


class AnimationFrameOut(BaseModel):
    r_max: float
    z_max: float
    r_emitter: float
    theta_r: float
    theta_s: float
    grid_res: int
    # Temps reel ecoule (s) pour chaque frame — meme convention que le titre
    # 'Drip Irrigation : t = ...' d'Animation2DIrrigation.m. Absent sur un
    # resultat produit par un engine plus ancien : optionnel, defaut vide.
    frame_times_s: list[float] = []
    frames: list[list[list[float]]]


class HistoryPointOut(BaseModel):
    date: str
    water_used_liters: float
    soil_moisture_percent: float
    severe_stress_alert: bool


class FarmerFieldSummaryOut(BaseModel):
    field_id: str
    farmer_name: str
    farmer_phone: str
    crop: str
    size_hectares: float
    needs_attention: bool


class RecommendationJobOut(BaseModel):
    id: str
    field_id: str
    status: str
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


class RunJobResponse(BaseModel):
    job_id: str
    status: str


class SimulationRunRequest(BaseModel):
    culture: Crop
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    size_hectares: float | None = Field(default=None, gt=0)
    type_sol: SoilType | None = None
    emitter_flow_lh: float | None = Field(default=None, gt=0)


class SimulationJobOut(BaseModel):
    id: str
    status: str
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


class SeasonSimulationIn(BaseModel):
    irrigation_coverage: float


class SeasonPointOut(BaseModel):
    day: int
    biomass: float
    rendement: float


class SeasonSimulationOut(BaseModel):
    points: list[SeasonPointOut]
    final_rendement: float
    appreciation: str


class SeasonSimulationDataDrivenIn(BaseModel):
    # Jours du cycle de croissance a tester (ex. [6, 9, 12], comme les
    # input() du script original d'Alex) et la valeur d'ETo (mm/jour) a
    # tester pour chacun — meme longueur.
    jours_test: list[int]
    eto_test: list[float]


class SeasonSimulationDataDrivenOut(BaseModel):
    rendement: float
    biomasse: float
    appreciation: str
