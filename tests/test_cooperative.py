def _login(client, phone):
    client.post("/auth/otp/request", json={"phone": phone})
    return client.post(
        "/auth/otp/verify", json={"phone": phone, "code": "1234"}
    ).json()["token"]


def test_cooperative_endpoint_requires_an_agent_role(client):
    farmer_token = _login(client, "+22990000000")

    response = client.get(
        "/cooperative/fields", headers={"Authorization": f"Bearer {farmer_token}"}
    )

    assert response.status_code == 403


def test_cooperative_agent_sees_managed_fields(client):
    farmer_token = _login(client, "+22990000000")
    client.post(
        "/fields",
        json={"crop": "mais", "size_hectares": 0.8, "latitude": 9.34, "longitude": 2.63, "planting_date": "2026-03-01"},
        headers={"Authorization": f"Bearer {farmer_token}"},
    )
    agent_token = _login(client, "+22911110000")

    response = client.get(
        "/cooperative/fields", headers={"Authorization": f"Bearer {agent_token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_agent_creates_a_farmer_account_without_otp(client):
    agent_token = _login(client, "+22911110000")

    response = client.post(
        "/cooperative/farmers",
        json={"phone": "+22990009999", "name": "Koffi Assogba"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["phone"] == "+22990009999"
    assert body["name"] == "Koffi Assogba"
    assert body["token"]


def test_agent_creates_a_farmer_account_without_a_name(client):
    agent_token = _login(client, "+22911110000")

    response = client.post(
        "/cooperative/farmers",
        json={"phone": "+22990008888", "name": None},
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    assert response.status_code == 201
    assert response.json()["name"] is None


def test_creating_a_farmer_twice_for_the_same_phone_conflicts(client):
    agent_token = _login(client, "+22911110000")
    client.post(
        "/cooperative/farmers",
        json={"phone": "+22990009999", "name": "Koffi Assogba"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    response = client.post(
        "/cooperative/farmers",
        json={"phone": "+22990009999", "name": "Autre Nom"},
        headers={"Authorization": f"Bearer {agent_token}"},
    )

    assert response.status_code == 409


def test_only_an_agent_can_create_a_farmer_account(client):
    farmer_token = _login(client, "+22990000000")

    response = client.post(
        "/cooperative/farmers",
        json={"phone": "+22990009999", "name": "Koffi Assogba"},
        headers={"Authorization": f"Bearer {farmer_token}"},
    )

    assert response.status_code == 403
