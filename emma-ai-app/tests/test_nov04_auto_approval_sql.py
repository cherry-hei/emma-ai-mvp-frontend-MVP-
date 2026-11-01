"""Optional disposable PostgreSQL tests with minimal source-shaped auth fixtures.

Opt in with AUTO_APPROVAL_SQL_TESTS=1; never connects to an existing cluster.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(os.getenv('AUTO_APPROVAL_SQL_TESTS') != '1', reason='disposable SQL opt-in')


@pytest.fixture(scope='module')
def sql():
    bindir = Path('/usr/lib/postgresql/16/bin')
    if not (bindir / 'initdb').exists():
        pytest.skip('PostgreSQL 16 binaries unavailable')
    root = Path(tempfile.mkdtemp(prefix='emma_auto_approval_'))
    database = 'auto_approval_' + uuid4().hex
    def command(args, **kw):
        return subprocess.run(args, check=True, text=True, capture_output=True, **kw)
    started = False
    try:
        command([str(bindir/'initdb'), '-D', str(root/'data'), '-A', 'trust', '--no-locale'])
        try:
            command([str(bindir/'pg_ctl'), '-D', str(root/'data'), '-l', str(root/'server.log'),
                     '-o', f"-k {root} -h '' -p 55439", '-w', 'start'])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError((root/'server.log').read_text()) from exc
        started = True
        command([str(bindir/'createdb'), '-h', str(root), '-p', '55439', database])
        def execute(statement):
            return command([str(bindir/'psql'), '-X', '-h', str(root), '-p', '55439',
                            '-d', database, '-v', 'ON_ERROR_STOP=1', '-At'], input=statement).stdout
        execute("""
        create role anon; create role authenticated;
        create schema auth;
        create function auth.uid() returns uuid language sql as
          $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
        create table organisations(id uuid primary key);
        create table facilities(id uuid primary key, org_id uuid references organisations(id));
        create table users_profile(id uuid primary key, auth_user_id uuid unique,
          org_id uuid, facility_id uuid references facilities(id), role text);
        insert into organisations values ('00000000-0000-0000-0000-000000000001');
        insert into facilities values ('00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001');
        insert into users_profile values
          ('00000000-0000-0000-0000-000000000003','00000000-0000-0000-0000-000000000004',
          '00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002','OWNER');
        """)
        execute((Path(__file__).parents[1]/'supabase/migrations/20261101000300_auto_approval.sql').read_text())
        yield execute
    finally:
        if started:
            subprocess.run([str(bindir/'dropdb'), '-h', str(root), '-p', '55439', database], capture_output=True)
            subprocess.run([str(bindir/'pg_ctl'), '-D', str(root/'data'), '-m', 'immediate', '-w', 'stop'], capture_output=True)
        shutil.rmtree(root)


PREFIX = "set role authenticated; set request.jwt.claim.sub='00000000-0000-0000-0000-000000000004';"
ARGS = "'00000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000002'"


def test_sql_cas_retry_audit_and_rls(sql):
    create = f"select auto_approval_write_policy({ARGS},0,'create',false,array['AL'],'rules-1');"
    first = sql(PREFIX + create)
    assert '"version": 1' in first and '"enabled": false' in first
    assert '"version": 1' in sql(PREFIX + create)
    assert 'conflict' in sql(PREFIX + create.replace("'rules-1'", "'changed'"))
    assert 'conflict' in sql(PREFIX + create.replace("'create'", "'other'"))
    assert '"version": 2' in sql(PREFIX + f"select auto_approval_write_policy({ARGS},1,'enable',true,array['AL'],'rules-1');")
    assert sql('select count(*) from auto_approval_policy_audit;').strip() == '2'
    with pytest.raises(subprocess.CalledProcessError):
        sql("update auto_approval_policy_audit set created_at=now();")
    with pytest.raises(subprocess.CalledProcessError):
        sql("delete from auto_approval_policy_audit;")
    # Direct writes cannot bypass CAS/audit even for the owner.
    with pytest.raises(subprocess.CalledProcessError):
        sql(PREFIX + 'update auto_approval_policies set enabled=false;')
    sql("update users_profile set role='NURSE_MGR';")
    assert sql(PREFIX + 'select count(*) from auto_approval_policies;').splitlines()[-1] == '0'
    with pytest.raises(subprocess.CalledProcessError):
        sql(PREFIX + create)
    sql("update users_profile set role='OWNER',org_id=null;")
    assert sql(PREFIX + f"select auto_approval_is_owner({ARGS});").splitlines()[-1] == 'f'
    # Facility and org must both match the authenticated profile's home.
    assert sql(PREFIX + "select auto_approval_is_owner('00000000-0000-0000-0000-000000000009','00000000-0000-0000-0000-000000000002');").splitlines()[-1] == 'f'
    with pytest.raises(subprocess.CalledProcessError):
        sql(PREFIX + create.replace('000000000001', '000000000009'))
