"""Offline contract tests, not an actual database transaction/RLS test."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from emma_core.services import publication, roster
from emma_core.importers.loader import _publish, LoadResult
from tests.test_optimize_service import build_store


def test_persisted_soft_mapping_is_tenant_version_run_scoped():
    db = build_store()
    db.data['violation_log'] = [
        {'id': 'current-row', 'facility_id': 'f1', 'roster_version_id': 'v1', 'validation_run_id': 'r1', 'severity': 'soft', 'resolved': False, 'omission_id': 'soft-1'},
        {'id': 'other-row', 'facility_id': 'f2', 'roster_version_id': 'v1', 'validation_run_id': 'r1', 'severity': 'soft', 'resolved': False, 'omission_id': 'soft-foreign'},
    ]
    args = dict(facility_id='f1', roster_version_id='v1', validation_run_id='r1')
    assert publication.resolve_persisted_soft_omission_row_ids(db, **args, approved_soft_omission_ids=['soft-1']) == ['current-row']
    for bad in [[], ['soft-foreign'], ['soft-1','soft-1']]:
        with pytest.raises(publication.PublishGateError):
            publication.resolve_persisted_soft_omission_row_ids(db, **args, approved_soft_omission_ids=bad)


def test_persisted_soft_mapping_rejects_missing_or_duplicate_fingerprint():
    db = build_store()
    row = {'id': 'row1', 'facility_id': 'f1', 'roster_version_id': 'v1', 'validation_run_id': 'r1', 'severity': 'soft', 'resolved': False}
    args = dict(facility_id='f1', roster_version_id='v1', validation_run_id='r1', approved_soft_omission_ids=['soft-1'])
    db.data['violation_log'] = [row]
    with pytest.raises(publication.PublishGateError):
        publication.resolve_persisted_soft_omission_row_ids(db, **args)
    db.data['violation_log'] = [{**row, 'omission_id': 'soft-1'}, {**row, 'id':'row2','omission_id':'soft-1'}]
    with pytest.raises(publication.PublishGateError):
        publication.resolve_persisted_soft_omission_row_ids(db, **args)


def test_atomic_rpc_has_exact_schema_parameter_names_and_no_post_rpc_write():
    calls=[]
    class Client:
        def rpc(self, name, params):
            calls.append((name, params)); return self
        def execute(self):
            return SimpleNamespace(data=[{'id':'v1','status':'published'}])
        def table(self, name):
            raise AssertionError('No non-atomic post-RPC audit/table mutation permitted')
    roster.publish_version(Client(), facility_id='f1',roster_version_id='v1',created_by='owner1',validation_run_id='run1',input_digest='a'*64,omitted_soft_violation_row_ids=['row1'])
    params=calls[0][1]
    assert set(params)=={'p_facility_id','p_roster_version_id','p_created_by','p_validation_run_id','p_input_digest','p_omitted_soft_violation_row_ids'}
    assert params['p_omitted_soft_violation_row_ids']==['row1']


def test_imported_workbook_cannot_auto_approve_or_omit_findings():
    class NoIO:
        def __getattr__(self, name):
            raise AssertionError('Import publication path must not write or auto-approve')
    result=LoadResult(mode='commit',facility_id='f1')
    _publish(NoIO(), 'f1','v1','owner1',result)
    assert result.warnings[0]['code']=='publication_review_required'


def test_migration_preserves_hard_and_exact_run_evidence_and_is_atomic():
    sql=(Path(__file__).parents[1]/'supabase/migrations/20261011000024_publish_soft_omissions.sql').read_text()
    assert 'drop function if exists public.publish_roster_version(uuid, uuid, uuid)' in sql
    for fragment in ['p_created_by is null',"up.role in ('OWNER', 'superintendent')",'source_content_updated_at is distinct from target.content_updated_at','validated_by is distinct from p_created_by','actual_hard_count <> 0','actual_unknown_count <> 0','soft_violation_count <> actual_soft_count','requested_omission_count <> actual_soft_count','score.hard_violation_count <> 0','insert into public.audit_logs','insert into public.roster_publish_events','for update']:
        assert fragment in sql
    assert 'score.constraint_score <' not in sql


def test_new_sql_parses_without_being_executed():
    from pglast import parse_sql
    sql=(Path(__file__).parents[1]/'supabase/migrations/20261011000024_publish_soft_omissions.sql').read_text()
    assert len(parse_sql(sql))==10
