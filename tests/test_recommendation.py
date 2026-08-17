from tests.test_fields import _login


def test_recommendation_includes_moisture_and_explanation(client):
    token = _login(client)
    field_id = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    response = client.get(
        f"/fields/{field_id}/recommendation",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert 0 <= body["soil_moisture_percent"] <= 100
    assert body["explanation"]


def test_history_points_include_a_severe_stress_flag(client):
    token = _login(client)
    field_id = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    response = client.get(
        f"/fields/{field_id}/history",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    assert len(body) == 14
    for point in body:
        assert isinstance(point["severe_stress_alert"], bool)
        assert point["severe_stress_alert"] == (point["soil_moisture_percent"] < 32)
