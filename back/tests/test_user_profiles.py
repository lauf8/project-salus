import pytest


@pytest.mark.parametrize("astronaut,physician", [(True, False), (False, True), (True, True)])
def test_profiles_persist_through_registration_and_login(client, astronaut, physician):
    payload = {
        "name": "Teste de perfil",
        "email": "profiles@example.com",
        "password": "test123456",
        "password_confirmation": "test123456",
        "is_astronaut": astronaut,
        "is_physician": physician,
    }
    response = client.post("/v1/users/", json=payload)
    assert response.status_code == 200
    assert response.json()["is_astronaut"] is astronaut
    assert response.json()["is_physician"] is physician
    login = client.post("/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert login.status_code == 200
    # A listagem é pública e pode conter a identidade pública criada pela API.
    user = next(row for row in client.get("/v1/users/").json()["data"] if row["email"] == payload["email"])
    assert user["is_astronaut"] is astronaut
    assert user["is_physician"] is physician


def test_registration_rejects_empty_profiles(client):
    response = client.post("/v1/users/", json={
        "name": "Teste", "email": "empty@example.com",
        "password": "test123456", "password_confirmation": "test123456",
        "is_astronaut": False, "is_physician": False,
    })
    assert response.status_code == 422


def test_psychologist_profile_registration(client):
    response = client.post('/v1/users/', json={
        'name': 'Psychologist', 'email': 'psychologist@example.com',
        'password': 'test123456', 'password_confirmation': 'test123456',
        'is_astronaut': False, 'is_physician': False, 'is_psychologist': True,
    })
    assert response.status_code == 200
    assert response.json()['is_psychologist'] is True
    assert response.json()['is_physician'] is False
