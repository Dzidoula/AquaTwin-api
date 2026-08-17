from typing import Literal

from pydantic import BaseModel

Crop = Literal["mais", "tomate", "coton"]


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


class FieldUpdate(BaseModel):
    size_hectares: float


class FieldOut(BaseModel):
    id: str
    crop: str
    size_hectares: float
    latitude: float
    longitude: float
    planting_date: str


class RecommendationOut(BaseModel):
    date: str
    should_irrigate: bool
    duration_minutes: int
    volume_liters: float
    severe_stress_alert: bool
    soil_moisture_percent: float
    explanation: str


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
