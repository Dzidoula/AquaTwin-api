from tests.test_fields import _login


def test_me_requires_a_token(client):
    response = client.get("/me")

    assert response.status_code == 401


def test_me_returns_the_current_user(client):
    token = _login(client, "+22990000000")

    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})

    body = response.json()
    assert response.status_code == 200
    assert body["phone"] == "+22990000000"
    assert body["role"] == "agriculteur"
    assert body["token"] == token


def test_patch_me_updates_the_name(client):
    token = _login(client, "+22990000000")

    response = client.patch(
        "/me", json={"name": "Kofi Adjovi"}, headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Kofi Adjovi"

    follow_up = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert follow_up.json()["name"] == "Kofi Adjovi"


def test_patch_me_requires_a_token(client):
    response = client.patch("/me", json={"name": "Kofi Adjovi"})

    assert response.status_code == 401
