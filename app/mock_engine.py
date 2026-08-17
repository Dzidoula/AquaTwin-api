"""Deterministic stand-ins for the real AquaTwin-Drip agronomic engine.

Not the real Richards-equation solver / AquaCrop / Random Forest engine
(mémoire chs. 3 & 6) — just enough structure to develop and test the mobile
app against realistic-shaped responses before that engine is exposed here.
"""

import hashlib
from datetime import date, timedelta


def _seeded_value(seed_text: str, low: float, high: float) -> float:
    digest = hashlib.sha256(seed_text.encode()).hexdigest()
    fraction = int(digest[:8], 16) / 0xFFFFFFFF
    return low + fraction * (high - low)


def today_recommendation(field_id: str, today: date) -> dict:
    seed = f"{field_id}:{today.isoformat()}"
    moisture = _seeded_value(seed + ":moisture", 25, 85)
    should_irrigate = moisture < 55
    severe_stress = moisture < 32
    duration = int(_seeded_value(seed + ":duration", 10, 30)) if should_irrigate else 0
    volume = round(_seeded_value(seed + ":volume", 8, 25), 1) if should_irrigate else 0.0
    if severe_stress:
        explanation = (
            f"Humidité du sol à {moisture:.0f}%, en dessous du seuil critique : "
            "stress hydrique sévère détecté, arrosage recommandé sans délai."
        )
    elif should_irrigate:
        explanation = (
            f"Humidité du sol à {moisture:.0f}%, sous le seuil optimal : "
            f"un arrosage de {duration} min ({volume:.0f} L) est recommandé aujourd'hui."
        )
    else:
        explanation = f"Humidité du sol à {moisture:.0f}%, au-dessus du seuil optimal : pas d'arrosage nécessaire aujourd'hui."
    return {
        "date": today.isoformat(),
        "should_irrigate": should_irrigate,
        "duration_minutes": duration,
        "volume_liters": volume,
        "severe_stress_alert": severe_stress,
        "soil_moisture_percent": round(moisture, 1),
        "explanation": explanation,
    }


def season_history(field_id: str, today: date, days: int = 14) -> list[dict]:
    points = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        seed = f"{field_id}:{day.isoformat()}"
        moisture = round(_seeded_value(seed + ":moisture", 25, 85), 1)
        points.append({
            "date": day.isoformat(),
            "water_used_liters": round(_seeded_value(seed + ":water", 0, 22), 1),
            "soil_moisture_percent": moisture,
            "severe_stress_alert": moisture < 32,
        })
    return points
