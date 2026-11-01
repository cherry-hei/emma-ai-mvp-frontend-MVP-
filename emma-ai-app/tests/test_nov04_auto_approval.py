"""Offline contract/security tests. No network or real customer fixtures."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
import asyncio
import httpx

from api.deps import get_ctx
from api.routers.auto_approval import router
from emma_core.services import auto_approval as svc

ORG, FAC, REQUEST = (str(uuid4()) for _ in range(3))


class Store:
    def __init__(self):
        self.policy = None
        self.audit = {}
        self.calls = []
        self.bad = False
        self.request = dict(id=REQUEST, facility_id=FAC, status="pending",
                            leave_type="AL", date_start="2099-01-01", date_end="2099-01-02")

    def table(self, name):
        self.calls.append(name)
        return Query(self, name)

    def rpc(self, name, args):
        assert name == "auto_approval_write_policy"
        self.calls.append(name)
        if self.bad is not False:
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.bad))
        payload = deepcopy(args)
        key = args['p_retry']
        if key in self.audit:
            old, result = self.audit[key]
            data = result if old == payload else {"error": "conflict"}
        elif args['p_expected'] != (self.policy['version'] if self.policy else 0):
            data = {"error": "conflict"}
        else:
            data = dict(org_id=args['p_org'], facility_id=args['p_facility'],
                        version=args['p_expected'] + 1, enabled=args['p_enabled'],
                        allowed_types=args['p_types'], rule_version=args['p_rule'])
            self.policy = deepcopy(data)
            self.audit[key] = (payload, deepcopy(data))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=deepcopy(data)))


class Query:
    def __init__(self, store, name):
        self.store, self.name, self.filters = store, name, {}

    def select(self, fields):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, n):
        assert n == 1
        return self

    def execute(self):
        if self.store.bad is not False:
            return SimpleNamespace(data=self.store.bad)
        row = self.store.policy if self.name == 'auto_approval_policies' else self.store.request
        rows = [deepcopy(row)] if row and all(row.get(k) == v for k, v in self.filters.items()) else []
        return SimpleNamespace(data=rows)


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, path, **kwargs):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(run())

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)


@pytest.fixture
def env(monkeypatch):
    # This sandbox stalls AnyIO thread wakeups. Exercise ASGI routing inline;
    # these tests do not establish the hosted worker/thread runtime.
    async def inline(func, *args, **kwargs):
        return func(*args, **kwargs)
    monkeypatch.setattr('fastapi.routing.run_in_threadpool', inline)
    monkeypatch.setattr('fastapi.dependencies.utils.run_in_threadpool', inline)
    store = Store()
    ctx = SimpleNamespace(profile=SimpleNamespace(role='OWNER'), org_id=ORG,
                          facility_id=FAC, client=store)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_ctx] = lambda: ctx
    yield ASGIClient(app), ctx, store


def payload(**kw):
    return dict(expected_version=0, retry_key="create-1", enabled=False,
                allowed_types=['AL'], rule_version='reviewed-rules-1', **kw)


def create(client):
    return client.post('/auto-approval/policy', json=payload())


def test_create_read_patch_retry_and_audit(env):
    client, ctx, store = env
    assert client.get('/auto-approval/policy').json()['policy'] is None
    assert create(client).status_code == 201
    assert create(client).json()['version'] == 1
    body = payload()
    body.update(expected_version=1, retry_key='activate-1', enabled=True)
    assert client.patch('/auto-approval/policy', json=body).json()['enabled'] is True
    assert client.patch('/auto-approval/policy', json=body).json()['version'] == 2
    assert client.get('/auto-approval/policy').json()['policy']['version'] == 2
    assert len(store.audit) == 2


@pytest.mark.parametrize('role', ['NURSE_MGR', 'FRONTLINE', 'ADMIN_CLERK', 'SCHEDULER', 'HR_AUDITOR', 'ALLIED_HEALTH', 'unknown', None])
@pytest.mark.parametrize('method,path', [('get','/policy'), ('post','/policy'), ('patch','/policy'), ('post',f'/evaluations/{REQUEST}')])
def test_nonowners_denied_before_persistence(env, role, method, path):
    client, ctx, store = env
    ctx.profile.role = role
    body = {'expected_policy_version': 1} if 'evaluations' in path else payload()
    response = getattr(client, method)('/auto-approval' + path, **({} if method == 'get' else {'json': body}))
    assert response.status_code == 403
    assert store.calls == []


@pytest.mark.parametrize('field', ['org_id', 'facility_id'])
def test_missing_scope_denied(env, field):
    client, ctx, store = env
    setattr(ctx, field, '')
    assert create(client).status_code == 403
    assert not store.calls


def test_cross_tenant_not_found(env):
    client, ctx, store = env
    store.request['facility_id'] = str(uuid4())
    assert client.post(f'/auto-approval/evaluations/{REQUEST}', json={'expected_policy_version': 1}).status_code == 404


@pytest.mark.parametrize('bad', [None, '', '<html>error</html>', {}, [], [None], {'error': 'db_error'}, {'version': 1}])
def test_malformed_write_not_success(env, bad):
    client, ctx, store = env
    store.bad = bad
    assert create(client).status_code == 503


@pytest.mark.parametrize('bad', [None, '', {}, [None], [{'version': 1}]])
def test_malformed_read_not_success(env, bad):
    client, ctx, store = env
    store.bad = bad
    assert client.get('/auto-approval/policy').status_code == 503


def test_cas_and_retry_conflicts(env):
    client, ctx, store = env
    assert create(client).status_code == 201
    body = payload()
    body['rule_version'] = 'different'
    assert client.post('/auto-approval/policy', json=body).status_code == 409
    body['retry_key'] = 'other-create'
    assert client.post('/auto-approval/policy', json=body).status_code == 409
    body.update(expected_version=7, retry_key='stale')
    assert client.patch('/auto-approval/policy', json=body).status_code == 409


@pytest.mark.parametrize('change', [dict(enabled=True), dict(allowed_types=['']), dict(allowed_types=['AL','AL']), dict(expected_version=1)])
def test_invalid_create(env, change):
    client, ctx, store = env
    body = payload()
    body.update(change)
    assert client.post('/auto-approval/policy', json=body).status_code == 422
    assert not store.calls


@pytest.mark.parametrize('scenario,reason', [('missing','policy_missing'), ('disabled','policy_disabled'), ('stale','stale_policy_version'), ('type','type_not_explicitly_allowed'), ('past','past_or_invalid_dates'), ('decided','request_not_pending'), ('active','transactional_automatic_apply_unavailable')])
def test_deterministic_manual_review(env, scenario, reason):
    client, ctx, store = env
    if scenario != 'missing':
        create(client)
        if scenario != 'disabled':
            body = payload()
            body.update(expected_version=1, retry_key='enable', enabled=True)
            assert client.patch('/auto-approval/policy', json=body).status_code == 200
    if scenario == 'type':
        store.request['leave_type'] = 'DO'
    if scenario == 'past':
        store.request['date_start'] = '2020-01-01'
    if scenario == 'decided':
        store.request['status'] = 'approved'
    version = 1 if scenario in ('disabled','stale','missing') else 2
    url = f'/auto-approval/evaluations/{REQUEST}'
    a = client.post(url, json={'expected_policy_version': version})
    b = client.post(url, json={'expected_policy_version': version})
    assert a.status_code == 200 and a.json() == b.json()
    assert reason in a.json()['reasons']
    assert a.json()['outcome'] == 'manual_review'
    assert a.json()['mutation_available'] is False and a.json()['applied'] is False
    assert store.request['status'] == ('approved' if scenario == 'decided' else 'pending')
    assert set(store.calls) <= {'auto_approval_policies', 'auto_approval_write_policy', 'leave_requests'}


def test_rejects_client_scores_and_scope(env):
    client, ctx, store = env
    assert client.post(f'/auto-approval/evaluations/{REQUEST}', json={'expected_policy_version':1,'score':1}).status_code == 422
    body = payload()
    body['org_id'] = str(uuid4())
    assert client.post('/auto-approval/policy', json=body).status_code == 422


@pytest.mark.parametrize('field,value', [('version','1'), ('enabled','false'), ('facility_id',str(uuid4())), ('org_id',str(uuid4()))])
def test_untrusted_policy_response_rejected(env, field, value):
    client, ctx, store = env
    create(client)
    store.bad = {**store.policy, field: value}
    assert create(client).status_code == 503
    store.bad = [store.bad]
    assert client.get('/auto-approval/policy').status_code == 503


@pytest.mark.parametrize('field,value', [('date_start','invalid'), ('date_end',None), ('status',None)])
def test_bad_request_evidence_fails_closed(env, field, value):
    client, ctx, store = env
    store.request[field] = value
    result = client.post(f'/auto-approval/evaluations/{REQUEST}', json={'expected_policy_version':1})
    assert result.status_code == 503 or (result.status_code == 200 and result.json()['applied'] is False)


def test_db_exception_not_success(env, monkeypatch):
    client, ctx, store = env
    def fail(*a, **kw):
        raise RuntimeError('offline database failure')
    monkeypatch.setattr(store, 'rpc', fail)
    assert create(client).status_code == 503
    monkeypatch.setattr(store, 'table', fail)
    assert client.get('/auto-approval/policy').status_code == 503


def test_activation_empty_allowlist_and_patch_zero_denied(env):
    client, ctx, store = env
    assert client.patch('/auto-approval/policy', json=payload()).status_code == 422
    create(client)
    body = payload()
    body.update(expected_version=1, retry_key='enable', enabled=True, allowed_types=[])
    assert client.patch('/auto-approval/policy', json=body).status_code == 422


def test_legacy_owner_and_literal_utf8(env):
    client, ctx, store = env
    ctx.profile.role = 'superintendent'
    body = payload()
    body['allowed_types'] = ['待確認假別']
    body['rule_version'] = '規則版本一'
    result = client.post('/auto-approval/policy', json=body)
    assert result.status_code == 201
    assert result.json()['allowed_types'] == ['待確認假別']
    assert result.json()['rule_version'] == '規則版本一'
