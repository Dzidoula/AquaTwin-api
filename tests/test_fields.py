def _login(client, phone="+22990000000"):
    client.post("/auth/otp/request", json={"phone": phone})
    return client.post(
        "/auth/otp/verify", json={"phone": phone, "code": "1234"}
    ).json()["token"]


def test_create_field_requires_a_token(client):
    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
    )

    assert response.status_code == 401


def test_create_field_owned_by_the_authenticated_user(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201


def test_another_farmer_cannot_update_someone_elses_field(client):
    owner_token = _login(client, phone="+22990000001")
    field_id = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {owner_token}"},
    ).json()["id"]

    other_token = _login(client, phone="+22990000002")
    response = client.patch(
        f"/fields/{field_id}",
        json={"size_hectares": 1.5},
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 403


def test_list_my_fields_returns_only_the_current_users_fields(client):
    owner_token = _login(client, "+22990000001")
    client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    other_token = _login(client, "+22990000002")
    client.post(
        "/fields",
        json={"crop": "tomate", "size_hectares": 1.2, "latitude": 9.35, "longitude": 2.64, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {other_token}"},
    )

    response = client.get(
        "/fields/mine", headers={"Authorization": f"Bearer {owner_token}"}
    )

    assert response.status_code == 200
    fields = response.json()
    assert len(fields) == 1
    assert fields[0]["crop"] == "mais"


def test_list_my_fields_requires_a_token(client):
    response = client.get("/fields/mine")

    assert response.status_code == 401


def test_create_field_requires_a_planting_date(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_field_returns_the_planting_date(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={
            "crop": "mais",
            "size_hectares": 0.8,
            "latitude": 9.34,
            "longitude": 2.63,
            "planting_date": "2026-03-01",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["planting_date"] == "2026-03-01"


def test_create_field_stores_the_farmer_supplied_soil_type(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={
            "crop": "mais", "size_hectares": 0.8, "latitude": 9.34,
            "longitude": 2.63, "planting_date": "2026-03-01", "soil_type": "sableux",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["soil_type"] == "sableux"


def test_create_field_defaults_soil_type_to_null_when_not_given(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["soil_type"] is None


def test_create_field_rejects_an_unknown_soil_type(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={
            "crop": "mais", "size_hectares": 0.8, "latitude": 9.34,
            "longitude": 2.63, "planting_date": "2026-03-01", "soil_type": "sable-lunaire",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_create_field_stores_the_farmer_supplied_emitter_flow_rate(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={
            "crop": "mais", "size_hectares": 0.8, "latitude": 9.34,
            "longitude": 2.63, "planting_date": "2026-03-01", "emitter_flow_lh": 4.0,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["emitter_flow_lh"] == 4.0


def test_create_field_defaults_emitter_flow_rate_to_null_when_not_given(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["emitter_flow_lh"] is None


def test_create_field_defaults_auto_recommend_enabled_to_false(client):
    token = _login(client)

    response = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["auto_recommend_enabled"] is False


def test_update_field_can_toggle_auto_recommend_without_touching_size(client):
    token = _login(client)
    field_id = client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {token}"},
    ).json()["id"]

    response = client.patch(
        f"/fields/{field_id}",
        json={"auto_recommend_enabled": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    field = client.get("/fields/mine", headers={"Authorization": f"Bearer {token}"}).json()[0]
    assert field["auto_recommend_enabled"] is True
    assert field["size_hectares"] == 0.8
