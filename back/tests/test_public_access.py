from app.core.roles import PROFILE_FIELDS


def test_public_identity_without_login(client):
    response = client.get('/v1/auth/public-user')
    assert response.status_code == 200
    user = response.json()
    assert user['is_global_admin'] is True
    assert 'hashed_password' not in user
    assert client.get('/v1/users/me').json()['id'] == user['id']
    assert client.get('/v1/users/').status_code == 200


def test_every_profile_can_be_selected_without_credentials(client):
    for profile in PROFILE_FIELDS:
        headers = {'X-Public-Profile': profile}
        response = client.get('/v1/auth/public-user', headers=headers)
        assert response.status_code == 200
        user = response.json()
        assert user[profile] is True
        headers['X-Public-User'] = str(user['id'])
        assert client.get('/v1/users/me', headers=headers).json()['id'] == user['id']


def test_invalid_public_selection(client):
    assert client.get('/v1/users/me', headers={'X-Public-Profile': 'invalid'}).status_code == 422
    assert client.get('/v1/users/me', headers={'X-Public-User': '99999'}).status_code == 404
