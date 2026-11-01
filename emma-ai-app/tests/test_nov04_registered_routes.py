"""Offline registration/authentication checks; never invoke a real database."""
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.mark.parametrize('path,methods', [
    ('/messages', {'get', 'post'}),
    ('/messages/contacts', {'get'}),
    ('/messages/{message_id}/read', {'patch'}),
    ('/request-windows', {'get', 'post'}),
    ('/request-windows/{window_id}', {'patch'}),
    ('/request-windows/duty', {'get'}),
    ('/me/request-window', {'get'}),
])
def test_candidate_registers_real_routes(path, methods):
    assert methods <= set(app.openapi()['paths'][path])


@pytest.mark.parametrize('path', [
    '/messages', '/messages/contacts', '/request-windows',
    '/request-windows/duty', '/me/request-window?kind=duty',
])
def test_no_anonymous_chat_or_window_access(path):
    response = TestClient(app).get(path)
    assert response.status_code == 401
    assert response.json()['detail']['code'] == 'unauthorized'
