"""Offline contracts for Demo-style UI; no network, account or database writes."""
from __future__ import annotations
from datetime import date
import pytest
from fastapi import HTTPException
from api.deps import require_read
from api.routers import roster as router
from emma_core.permissions import Feature
from emma_core.services import roster, reports, roster_history
from tests.test_optimize_service import FakeSupabase
from tests.test_phase5_api_security import _ctx


def store():
    db = FakeSupabase()
    db.data.update({
        '_seq': 1,
        'roster_periods': [
            {'id': 'pa', 'facility_id': 'fa', 'period_start': '2026-10-01', 'period_end': '2026-10-31'},
            {'id': 'pb', 'facility_id': 'fb', 'period_start': '2026-10-01', 'period_end': '2026-10-31'},
        ],
        'roster_versions': [
            {'id': 'va', 'facility_id': 'fa', 'period_id': 'pa', 'version_type': 'manual', 'status': 'draft'},
            {'id': 'vb', 'facility_id': 'fb', 'period_id': 'pb', 'version_type': 'manual', 'status': 'draft'},
            {'id': 'vpub', 'facility_id': 'fa', 'period_id': 'pa', 'version_type': 'manual', 'status': 'published'},
        ],
        'facilities': [{'id': 'fa', 'org_id': 'oa'}, {'id': 'fb', 'org_id': 'ob'}],
        'staff': [
            {'id': 'sa', 'facility_id': 'fa', 'name': 'Synthetic A', 'rank': 'RN', 'employment_type': 'local_ft'},
            {'id': 'sb', 'facility_id': 'fb', 'name': 'Synthetic B', 'rank': 'HW', 'employment_type': 'local_pt'},
        ],
        'shift_definitions': [
            {'id': 'da', 'org_id': 'oa', 'shift_type': 'D', 'start_time': '09:00', 'end_time': '17:00', 'paid_minutes': 435, 'cross_midnight': False, 'is_working': True},
            {'id': 'db', 'org_id': 'ob', 'shift_type': 'D', 'start_time': '09:00', 'end_time': '18:00', 'paid_minutes': 495, 'cross_midnight': False, 'is_working': True},
        ],
        'shifts': [
            {'id': 'sha', 'facility_id': 'fa', 'roster_version_id': 'va', 'date': '2026-10-01', 'shift_type': 'D', 'start_time': '09:00', 'end_time': '17:00', 'paid_minutes': 435, 'is_working': True},
            {'id': 'shb', 'facility_id': 'fb', 'roster_version_id': 'vb', 'date': '2026-10-01', 'shift_type': 'D', 'start_time': '09:00', 'end_time': '18:00', 'paid_minutes': 495, 'is_working': True},
        ],
        'shift_assignments': [
            {'id': 'aa', 'facility_id': 'fa', 'shift_id': 'sha', 'staff_id': 'sa', 'status': 'assigned', 'tasks': ['task-a']},
            {'id': 'ab', 'facility_id': 'fb', 'shift_id': 'shb', 'staff_id': 'sb', 'status': 'assigned', 'tasks': ['task-b']},
        ],
        'roster_publish_events': [
            {'id': 'ea', 'facility_id': 'fa', 'roster_version_id': 'va', 'event_type': 'save_draft', 'created_at': '2026-10-01T09:00:00Z'},
            {'id': 'eb', 'facility_id': 'fb', 'roster_version_id': 'vb', 'event_type': 'publish', 'created_at': '2026-10-01T09:00:00Z'},
        ],
        'audit_logs': [
            {'id': 'la', 'facility_id': 'fa', 'entity_table': 'shift_assignments', 'action': 'update', 'after_json': {'roster_version_id': 'va', 'shift_type': 'D'}, 'created_at': '2026-10-01T09:00:00Z', 'reason': '=HYPERLINK("https://example.invalid")'},
            {'id': 'lb', 'facility_id': 'fb', 'entity_table': 'shift_assignments', 'action': 'update', 'after_json': {'roster_version_id': 'vb'}, 'created_at': '2026-10-01T09:00:00Z'},
            {'id': 'null', 'facility_id': None, 'entity_table': 'roster_versions', 'entity_id': 'va', 'action': 'publish', 'created_at': '2026-10-01T09:00:00Z'},
        ],
    })
    return db


def test_two_organisations_keep_different_same_code_definitions():
    db = store()
    assert [d.paid_minutes for d in roster.get_shift_defs(db, 'fa')] == [435]
    assert [d.paid_minutes for d in roster.get_shift_defs(db, 'fb')] == [495]


def test_grid_paid_minutes_match_same_saved_version_and_org():
    db = store()
    ga = roster.get_roster_grid(db, 'fa', 'pa', version_id='va')
    gb = roster.get_roster_grid(db, 'fb', 'pb', version_id='vb')
    assert ga.rows[0].cells[0].paid_minutes == 435
    assert gb.rows[0].cells[0].paid_minutes == 495
    assert ga.rows[0].cells[0].tasks == ['task-a']
    assert roster.get_roster_grid(db, 'fa', 'pa', version_id='vb').version_id is None


def test_selected_draft_report_not_silently_operative_published_version():
    db = store()
    selected = reports.generate(db, 'fa', 'roster_export', params={'period_id': 'pa', 'version_id': 'va'}, persist=False)
    assert selected['payload']['meta']['roster_version_id'] == 'va'
    assert selected['payload']['rows'][0]['paid_hours'] == 7.25
    assert selected['payload']['rows'][0]['tasks'] == 'task-a'
    assert selected['payload']['meta']['roster_version_status'] == 'draft'


@pytest.mark.parametrize('period,version', [('pb','vb'), ('pa','vb'), ('missing','va')])
def test_reports_reject_cross_facility_or_wrong_period_version(period, version):
    with pytest.raises(ValueError):
        reports.generate(store(), 'fa', 'roster_export', params={'period_id': period, 'version_id': version}, persist=False)


def test_aggregate_kpi_report_rejects_unsupported_selected_version():
    with pytest.raises(ValueError, match='does not support'):
        reports.generate(store(), 'fa', 'compliance_summary', params={'period_id': 'pa', 'version_id': 'va'}, persist=False)


def test_history_is_facility_and_version_scoped_read_only():
    db=store()
    before=repr(db.data)
    result=roster_history.read_history(db,'fa','pa','va',include_audit=True)
    assert [row['id'] for row in result['changes']] == ['la']
    assert [row['id'] for row in result['publish_events']] == ['ea']
    assert 'actor_email' not in result['changes'][0]
    assert not result['truncated']
    assert repr(db.data)==before
    assert "'=HYPERLINK" in roster_history.audit_csv(result)


def test_history_keeps_audit_hidden_without_grant():
    result=roster_history.read_history(store(),'fa','pa','va',include_audit=False)
    assert result['changes']==[] and not result['can_read_audit']
    assert len(result['publish_events'])==1


@pytest.mark.parametrize('role', ['FRONTLINE','ALLIED_HEALTH','NURSE_MGR','SCHEDULER','ADMIN_CLERK'])
def test_original_audit_download_rbac_not_widened(role):
    with pytest.raises(HTTPException) as exc:
        require_read(Feature.AUDIT_LOG)(_ctx(store(),role=role))
    assert exc.value.status_code==403


@pytest.mark.parametrize('role', ['OWNER','HR_AUDITOR'])
def test_audit_existing_authorised_roles_kept(role):
    assert require_read(Feature.AUDIT_LOG)(_ctx(store(),role=role))


def test_truncated_csv_fails_not_incomplete_export():
    with pytest.raises(ValueError,match='limit'):
        roster_history.audit_csv({'truncated':True,'changes':[]})


def scoped_ctx(db, role='OWNER'):
    from api.deps import AuthCtx
    from emma_core.models import Profile
    return AuthCtx(token='invalid-local-test', client=db,
        profile=Profile(id='test-profile', facility_id='fa', role=role))


@pytest.mark.parametrize('role', ['OWNER','NURSE_MGR','SCHEDULER','superintendent','scheduler'])
def test_draft_write_existing_edit_roles_can_pass_scope(role):
    assert router._authorize_draft(scoped_ctx(store(),role),'va',on_date=date(2026,10,1))['id']=='va'


@pytest.mark.parametrize('role', ['FRONTLINE','ADMIN_CLERK','ALLIED_HEALTH','HR_AUDITOR','staff','admin'])
def test_draft_write_read_only_or_self_roles_cannot_edit(role):
    with pytest.raises(HTTPException) as exc:
        router._authorize_draft(scoped_ctx(store(),role),'va',on_date=date(2026,10,1))
    assert exc.value.status_code==403


@pytest.mark.parametrize('version,day,status', [('vb',date(2026,10,1),404),('vpub',date(2026,10,1),409),('va',date(2026,9,30),422),('va',date(2026,11,1),422)])
def test_draft_write_cannot_cross_facility_published_or_month(version,day,status):
    with pytest.raises(HTTPException) as exc:
        router._authorize_draft(scoped_ctx(store()),version,on_date=day)
    assert exc.value.status_code==status
