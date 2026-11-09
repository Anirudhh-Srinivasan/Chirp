from datetime import datetime, timedelta, timezone

import jwt

from backend.config import settings


def test_signup_and_duplicates(client):
    data = {'username': 'Alice', 'email': 'Alice@example.com', 'password': 'password123'}
    response = client.post('/signup', json=data)
    assert response.status_code == 201
    assert response.json()['username'] == 'alice'
    assert 'password_hash' not in response.json()
    assert client.post('/signup', json=data).status_code == 409
    data['username'] = 'someone_else'
    assert client.post('/signup', json=data).status_code == 409


def test_signup_validation(client):
    for username, email, password in [('a', 'a@example.com', 'password123'),
                                      ('alice', 'bad-email', 'password123'),
                                      ('alice', 'a@example.com', 'short'),
                                      ('alice', 'a@example.com', '🔐' * 20)]:
        assert client.post('/signup', json=dict(username=username, email=email, password=password)).status_code == 422


def test_login_and_me(client, headers):
    assert client.get('/me', headers=headers).json()['username'] == 'alice'
    assert client.post('/login', json={'username': 'ALICE', 'password': 'password123'}).status_code == 200
    for username in ['alice', 'unknown']:
        assert client.post('/login', json={'username': username, 'password': 'wrong'}).status_code == 401


def test_auth_rejects_invalid_expired_and_deleted_user(client):
    now = datetime.now(timezone.utc)
    tokens = ['bad.token', jwt.encode({'sub': '1', 'iat': now, 'exp': now - timedelta(seconds=1)}, settings.secret_key, algorithm='HS256'),
              jwt.encode({'sub': '999', 'iat': now, 'exp': now + timedelta(minutes=1)}, settings.secret_key, algorithm='HS256')]
    assert client.post('/posts', json={'content': 'hello'}).status_code == 401
    for token in tokens:
        assert client.get('/me', headers={'Authorization': f'Bearer {token}'}).status_code == 401


def test_posts_persist_order_and_paginate(client, headers):
    first = client.post('/posts', headers=headers, json={'content': ' first post '})
    assert first.status_code == 201
    assert first.json()['content'] == 'first post'
    second = client.post('/posts', headers=headers, json={'content': 'second post'}).json()
    feed = client.get('/posts').json()
    assert [p['id'] for p in feed] == [second['id'], first.json()['id']]
    assert feed[0]['username'] == 'alice'
    assert feed[0]['created_at'].endswith('Z')
    assert len(client.get(f"/posts?before={second['id']}&limit=1").json()) == 1
    for content in ['', '  ', 'x' * 281]:
        assert client.post('/posts', headers=headers, json={'content': content}).status_code == 422


def test_like_toggle_and_owner_delete(client, headers):
    post = client.post('/posts', headers=headers, json={'content': 'hello'}).json()
    path = f"/posts/{post['id']}"
    liked = client.post(path + '/like', headers=headers).json()
    assert liked['like_count'] == 1 and liked['liked_by_me']
    assert client.get('/posts', headers=headers).json()[0]['liked_by_me']
    assert client.post(path + '/like', headers=headers).json()['like_count'] == 0
    client.post('/signup', json={'username': 'bob', 'email': 'bob@example.com', 'password': 'password123'})
    token = client.post('/login', json={'username': 'bob', 'password': 'password123'}).json()['access_token']
    assert client.delete(path, headers={'Authorization': f'Bearer {token}'}).status_code == 403
    client.post(path + '/like', headers=headers)
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get('/posts').json() == []
    assert client.post(path + '/like', headers=headers).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404


def test_health_and_cors(client):
    assert client.get('/health').json() == {'status': 'ok'}
    response = client.options('/posts', headers={'Origin': 'http://localhost:5500', 'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'authorization,content-type'})
    assert response.headers['access-control-allow-origin'] == 'http://localhost:5500'
    blocked = client.options('/posts', headers={'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'POST'})
    assert 'access-control-allow-origin' not in blocked.headers
