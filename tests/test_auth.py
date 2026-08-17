def test_verify_otp_returns_a_token(client):
    response = client.post(
        "/auth/otp/verify", json={"phone": "+22990000000", "code": "1234"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert isinstance(body["token"], str)


def test_verify_otp_rejects_wrong_code(client):
    response = client.post(
        "/auth/otp/verify", json={"phone": "+22990000000", "code": "0000"}
    )

    assert response.status_code == 401


def test_verify_otp_returns_a_null_name_for_self_registered_users(client):
    response = client.post(
        "/auth/otp/verify", json={"phone": "+22990000000", "code": "1234"}
    )

    assert response.status_code == 200
    assert response.json()["name"] is None
