import os
import pytest
from app import app, db, HealthCheck

# Set up test environment
os.environ['TESTING']='True'

@pytest.fixture
def client():
    # Create a test client for the Flask Application
    app.config["TESTING"] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client    
        with app.app_context():
            db.session.remove()
            db.drop_all()

def test_success(client):
    response = client.get('/healthz')
    assert response.status_code == 200

@pytest.mark.parametrize('method', ['post', 'put', 'delete','patch','options','head'])
def test_method_not_allowed(client, method):
    response = getattr(client,method)('/healthz')
    assert response.status_code == 405

def test_bad_request(client):
    response = client.get('/healthz', data={'random': '12345'})
    assert response.status_code == 400

def test_service_unavailable(client, monkeypatch):
    # Simulating database error
    def mock_commit():
        raise Exception("Database error")
    
    monkeypatch.setattr(db.session, 'commit', mock_commit)
    response = client.get('/healthz')
    assert response.status_code == 503