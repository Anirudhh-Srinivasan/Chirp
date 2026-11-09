from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend import models
from backend.migrations import upgrade


def account(client, name):
    response = client.post('/signup', json={'username': name, 'email': f'{name}@example.com', 'password': 'password123'})
    assert response.status_code == 201
    token = client.post('/login', json={'username': name, 'password': 'password123'}).json()['access_token']
    return response.json()['id'], {'Authorization': f'Bearer {token}'}


def test_follow_unfollow_edges_and_profile_privacy(client, headers):
    alice = client.get('/me', headers=headers).json()['id']
    bob, _ = account(client, 'bob')
    path = f'/users/{bob}/follow'
    assert client.post(path).status_code == 401
    assert client.delete(path).status_code == 401
    assert client.post(f'/users/{alice}/follow', headers=headers).status_code == 400
    assert client.delete(f'/users/{alice}/follow', headers=headers).status_code == 400
    for method in [client.post, client.delete]:
        assert method('/users/999/follow', headers=headers).status_code == 404
    for _ in range(2):
        response = client.post(path, headers=headers)
        assert response.status_code == 200
        assert response.json()['follower_count'] == 1
        assert response.json()['followed_by_me'] is True
    profile = client.get(f'/users/{bob}').json()
    assert profile['followed_by_me'] is False
    assert 'email' not in profile and 'password_hash' not in profile
    assert datetime.fromisoformat(profile['joined_at'].replace('Z', '+00:00')).tzinfo
    assert client.get(f'/users/{alice}').json()['following_count'] == 1
    assert [u['id'] for u in client.get(f'/users/{bob}/followers').json()] == [alice]
    assert [u['id'] for u in client.get(f'/users/{alice}/following').json()] == [bob]
    for _ in range(2):
        response = client.delete(path, headers=headers)
        assert response.json()['follower_count'] == 0
        assert response.json()['followed_by_me'] is False
    assert client.get(f'/users/{bob}/followers').json() == []


def test_following_feed_pagination_and_profile_posts(client, headers):
    bob, bob_headers = account(client, 'bob')
    _, charlie_headers = account(client, 'charlie')
    assert client.get('/posts?feed=following').status_code == 401
    assert client.get('/posts?feed=following', headers=headers).json() == []
    first = client.post('/posts', headers=bob_headers, json={'content': 'bob first'}).json()
    client.post('/posts', headers=headers, json={'content': 'own excluded'})
    client.post('/posts', headers=charlie_headers, json={'content': 'stranger excluded'})
    second = client.post('/posts', headers=bob_headers, json={'content': 'bob second'}).json()
    client.post(f'/users/{bob}/follow', headers=headers)
    feed = client.get('/posts?feed=following&limit=1', headers=headers).json()
    assert [p['id'] for p in feed] == [second['id']]
    older = client.get(f"/posts?feed=following&limit=1&before={second['id']}", headers=headers).json()
    assert [p['id'] for p in older] == [first['id']]
    assert [p['id'] for p in client.get(f'/posts?user_id={bob}').json()] == [second['id'], first['id']]
    client.delete(f'/users/{bob}/follow', headers=headers)
    assert client.get('/posts?feed=following', headers=headers).json() == []
    assert client.get('/posts?user_id=999').status_code == 404


def test_connections_pagination(client, headers):
    alice = client.get('/me', headers=headers).json()['id']
    bob, bob_headers = account(client, 'bob')
    charlie, charlie_headers = account(client, 'charlie')
    for auth in [bob_headers, charlie_headers]:
        client.post(f'/users/{alice}/follow', headers=auth)
    assert client.get(f'/users/{alice}/followers?limit=1').json()[0]['id'] == charlie
    assert client.get(f'/users/{alice}/followers?limit=1&before={charlie}').json()[0]['id'] == bob
    assert client.get('/users/999/followers').status_code == 404


def test_search_literal_matching_pagination_and_privacy(client, headers):
    first_id, _ = account(client, 'match_one')
    second_id, _ = account(client, 'match_two')
    first = client.post('/posts', headers=headers, json={'content': 'A MATCH with 100%_literal'}).json()
    second = client.post('/posts', headers=headers, json={'content': 'another match'}).json()
    response = client.get('/search?q=MaTcH&limit=1', headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data['users'][0]['id'] == second_id
    assert data['posts'][0]['id'] == second['id']
    assert 'email' not in data['users'][0]
    page = client.get(f"/search?q=match&limit=1&user_before={data['next_user_before']}&post_before={data['next_post_before']}").json()
    assert page['users'][0]['id'] == first_id
    assert page['posts'][0]['id'] == first['id']
    assert page['next_user_before'] is None and page['next_post_before'] is None
    assert len(client.get('/search', params={'q': '%_'}).json()['posts']) == 1
    assert client.get('/search', params={'q': "' OR 1=1 --"}).json()['posts'] == []
    assert client.get('/search?q=unmatched').json()['users'] == []
    for query in ['', '  ', 'x' * 101]:
        assert client.get('/search', params={'q': query}).status_code == 422
    assert client.get('/search?q=match&limit=0').status_code == 422


def test_legacy_upgrade_preserves_data_is_repeatable_and_adds_indexes(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(30), email VARCHAR(254), password_hash VARCHAR(128))')
        conn.exec_driver_sql("INSERT INTO users VALUES (1, 'legacy', 'legacy@example.com', 'existing_hash')")
        conn.exec_driver_sql('CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, created_at DATETIME)')
        conn.exec_driver_sql("INSERT INTO posts VALUES (1, 1, 'keep this', '2026-01-01 12:00:00')")
    upgrade(engine)
    upgrade(engine)
    with Session(engine) as db:
        assert db.get(models.User, 1).password_hash == 'existing_hash'
        assert db.get(models.User, 1).joined_at is None
        assert db.get(models.Post, 1).content == 'keep this'
        db.add(models.User(username='new_user', email='new@example.com', password_hash='hash'))
        db.commit()
        assert db.scalar(select(models.User).where(models.User.username == 'new_user')).joined_at is not None
        db.add(models.Follow(follower_id=1, followed_id=1))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(models.Follow(follower_id=1, followed_id=2))
        db.commit()
        db.add(models.Follow(follower_id=1, followed_id=2))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    inspector = inspect(engine)
    assert {'ix_posts_user_id_id', 'ix_posts_user_created_id', 'ix_posts_created_at'} <= {i['name'] for i in inspector.get_indexes('posts')}
    assert 'ix_follows_followed_follower' in {i['name'] for i in inspector.get_indexes('follows')}
    # Check the important equality + cursor/reverse lookups can actually use indexes.
    with engine.connect() as conn:
        plans = {
            'ix_posts_user_id_id': 'SELECT id FROM posts WHERE user_id=1 AND id<100 ORDER BY id DESC LIMIT 20',
            'ix_follows_followed_follower': 'SELECT follower_id FROM follows WHERE followed_id=2 ORDER BY follower_id DESC LIMIT 20',
            'ix_posts_user_created_id': 'SELECT id FROM posts WHERE user_id=1 ORDER BY created_at DESC, id DESC LIMIT 20',
        }
        for index, sql in plans.items():
            details = ' '.join(row[3] for row in conn.exec_driver_sql('EXPLAIN QUERY PLAN ' + sql))
            assert index in details
    engine.dispose()
