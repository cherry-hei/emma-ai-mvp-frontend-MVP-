"""Disposable CORS app tests. Never contact the configured API or database."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import pytest
from emma_core.config import Settings


def app_for(settings):
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                       allow_origin_regex=settings.allowed_origin_regex,
                       allow_methods=['*'], allow_headers=['*'], allow_credentials=True)
    return TestClient(app)


@pytest.mark.parametrize('origin', [
    'https://emma-ai-staff-pwa.vercel.app',
    'https://emma-ai-manager-mvp.vercel.app',
])
def test_exact_owned_vercel_origins_allowed(origin):
    settings = Settings(_env_file=None)
    client = app_for(settings)
    r = client.options('/auth/login', headers={'Origin': origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,authorization'})
    assert r.status_code == 200
    assert r.headers['access-control-allow-origin'] == origin


@pytest.mark.parametrize('origin', [
    'https://unrelated.vercel.app',
    'https://emma-ai-staff-pwa.vercel.app.attacker.invalid',
    'https://unrelated.manus.space',
])
def test_other_shared_hosting_not_granted(origin):
    client = app_for(Settings(_env_file=None))
    r = client.options('/auth/login', headers={'Origin': origin,
        'Access-Control-Request-Method': 'POST'})
    assert r.status_code == 400
    assert 'access-control-allow-origin' not in r.headers


def test_deployed_allowlist_requires_effective_environment_update():
    settings = Settings(_env_file=None, cors_origins='https://approved.invalid', cors_origin_regex='')
    assert settings.allowed_origins == ['https://approved.invalid']
    r = app_for(settings).options('/auth/login', headers={
        'Origin': 'https://emma-ai-staff-pwa.vercel.app',
        'Access-Control-Request-Method': 'POST'})
    assert r.status_code == 400
