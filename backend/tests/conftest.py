import os
import secrets

# Set configuration before importing the app; no developer database is touched.
os.environ['SECRET_KEY'] = secrets.token_urlsafe(48)
os.environ['DATABASE_URL'] = 'sqlite://'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.main import app


@pytest.fixture
def client():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def headers(client):
    client.post('/signup', json={'username': 'alice', 'email': 'alice@example.com', 'password': 'password123'})
    token = client.post('/login', json={'username': 'alice', 'password': 'password123'}).json()['access_token']
    return {'Authorization': f'Bearer {token}'}
