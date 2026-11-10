"""Synthetic config -> CP-SAT -> saved version -> authenticated linked export."""
from copy import deepcopy
from datetime import date, timedelta
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.deps import AuthCtx, get_ctx
from api.main import app
from api.routers import optimize as router
from emma_core.models import OptimizeRequest, Profile, SolverLimitsModel
from emma_core.services import naac_export, optimize, roster_analysis, validation
from tests.test_optimize_service import build_store


def profile():
    codes = []
    for code, minutes, working in [("A",480,True),("P",480,True),("O",0,False),("AL",480,False),("PH",0,False),("NO",0,False)]:
        codes.append({"code":code,"credit_minutes":minutes,"is_working":working,"active":True,
                      "am":int(code=="A"),"pm":int(code=="P"),"ph":int(code=="PH"),
                      "al":int(code=="AL"),"source":"Invented test dictionary"})
    return {"schema_version":1,"label":"Invented test profile","status":"confirmed",
            "evidence":["Synthetic test; not a facility policy"],"codes":codes,
            "roles":[{"rank":"CW","weekly_minutes":2640,"ph_minutes":480,
                      "min_rest_minutes":660,"max_weekly_minutes":2640,
                      "allowed_codes":["A","P"],"leave_codes":{"annual":"AL"}}],
            "demand":[{"code":"A","rank":"CW","weekdays":[0,1,2,3,4],"count":1,"source":"Invented planning target"}],
            "off_code":"O","duty_officer_task_code":"#","holiday_dates":["2026-12-25","2026-12-26","2027-01-01"]}


def store():
    db=build_store();d=db.data
    d["roster_periods"][0].update(period_start="2026-11-30",period_end="2027-01-10",cycle_type="42day")
    d["staff"]=[s for s in d["staff"] if s["rank"]=="CW"]
    for i,s in enumerate(d["staff"]): s.update(name=f"Invented worker {i+1}",gender="F")
    d["shifts"]=[];d["shift_assignments"]=[]
    d["shift_definitions"]=[
        {"id":"def-a","org_id":"org-1","facility_id":"f1","shift_type":"A","start_time":"07:00","end_time":"15:00","paid_minutes":480,"is_working":True},
        {"id":"def-p","org_id":"org-1","facility_id":"f1","shift_type":"P","start_time":"13:00","end_time":"21:00","paid_minutes":480,"is_working":True},
    ]
    d["facility_json_configs"]=[{"id":"cfg1","facility_id":"f1","config_key":"roster_analysis","active":True,"version":1,"config_json":profile()}]
    d['shift_definitions'].extend({'id':'def-'+c['code'],'org_id':'org-1','facility_id':'f1','shift_type':c['code'],'paid_minutes':c['credit_minutes'],'is_working':False} for c in profile()['codes'] if not c['is_working'])
    return db


def solve(db):
    snap=roster_analysis.freeze(db,"f1","cfg1",db.data["roster_periods"][0])
    request=OptimizeRequest(facility_id="f1",period_id="p1",source_version_id="mv1",analysis_config_id="cfg1",
                            analysis_snapshot=snap,plan_mode="C",solver_limits=SolverLimitsModel(max_seconds=2,workers=1))
    result=optimize.run_optimization(db,request)
    return result.roster_options[0].roster_version_id


def test_blank_generation_preserves_leave_and_exports_frozen_formula_profile():
    db=store()
    db.data["leave_requests"]=[{"id":"al1","facility_id":"f1","staff_id":"cw1","leave_type":"annual","status":"approved","date_start":"2026-12-01","date_end":"2026-12-01"}]
    version=solve(db)
    assert version
    context=naac_export.load_context(db,"f1","p1",version)
    assert len(context["assignments"])==84
    shifts={s["id"]:s for s in context["shifts"]}
    codes={(a["staff_id"],shifts[a["shift_id"]]["date"]):shifts[a["shift_id"]]["shift_type"] for a in context["assignments"]}
    assert codes["cw1","2026-12-01"]=="AL"
    db.data["facility_json_configs"][0]["config_json"]["roles"][0]["weekly_minutes"]=60
    content,status=naac_export.export(db,"f1","p1",version_id=version)
    wb=load_workbook(BytesIO(content))
    assert status=="draft" and wb.sheetnames==list(roster_analysis.SHEETS)
    assert wb["Hours"]["BO5"].value==44  # frozen, not current edited profile
    assert wb["Hours"]["BF5"].value is None
    assert '待資料' in wb["Hours"]["BL5"].value
    assert '代號及時數' in wb["Hours"]["C5"].value
    assert wb["第一週"]["G5"].value=="AL"
    assert 'SUMIF' in wb["N更男女"]["D9"].value
    assert "'第一週'!E5" in wb['DO更次數']['D5'].value
    assert all(c.data_type!='e' for s in wb for row in s for c in row)


def test_weekly_cap_is_enforced_in_each_complete_week():
    db=store();version=solve(db)
    context=naac_export.load_context(db,"f1","p1",version)
    shifts={s["id"]:s for s in context["shifts"]}
    totals={}
    for a in context["assignments"]:
        s=shifts[a["shift_id"]];d=date.fromisoformat(s["date"])
        key=(a["staff_id"],d-timedelta(days=d.weekday()))
        totals[key]=totals.get(key,0)+s["paid_minutes"]
    assert len(totals)==12 and max(totals.values())<=2640


def test_draft_cannot_publish_just_because_solver_succeeded():
    db=store();version=solve(db)
    result=validation.validate_roster(db,'f1',version,persist=False)
    assert result['passes'] is False
    assert any(v['rule_code']=='analysis_review_required' for v in result['violations'])


def test_failed_writeback_stays_incomplete_and_old_draft_survives(monkeypatch):
    db=store()
    db.data['roster_versions'].append({'id':'old','facility_id':'f1','period_id':'p1','version_type':'C','status':'draft'})
    def fail(*args): raise RuntimeError('Simulated persistence failure')
    monkeypatch.setattr(optimize,'_writeback_analysis_nonworking',fail)
    with pytest.raises(RuntimeError,match='Simulated'):solve(db)
    assert next(v for v in db.data['roster_versions'] if v['id']=='old')['status']=='draft'
    partial=db.data['roster_versions'][-1]
    assert partial['status']=='archived' and 'analysis incomplete' in partial['label']
    with pytest.raises(ValueError,match='did not finish'):
        naac_export.export(db,'f1','p1',version_id=partial['id'])
    result=validation.validate_roster(db,'f1',partial['id'],persist=False)
    assert any(v['rule_code']=='analysis_review_required' for v in result['violations'])


def test_dictionary_credit_conflicts_fail_before_writeback():
    db=store();db.data['shift_definitions'][0]['paid_minutes']=420
    with pytest.raises(ValueError,match='credit mismatch'):solve(db)
    assert len(db.data['roster_versions'])==1


@pytest.mark.parametrize('change', ['duplicate','overlap','retired','unmapped'])
def test_ambiguous_profiles_rejected(change):
    p=profile()
    if change=='duplicate':p['codes'].append(deepcopy(p['codes'][0]))
    if change=='overlap':p['demand'].append(deepcopy(p['demand'][0]))
    if change=='retired':p['codes'][0]['active']=False
    if change=='unmapped':p['demand'][0]['rank']='missing'
    with pytest.raises(ValueError):roster_analysis.parse(p)


def test_source_empty_failure_does_not_archive_previous_draft():
    db=store();db.data['roster_versions'].append({'id':'old','facility_id':'f1','period_id':'p1','status':'draft','version_type':'C'})
    with pytest.raises(ValueError,match='no working demand'):
        optimize.run_optimization(db,OptimizeRequest(facility_id='f1',period_id='p1'))
    assert db.data['roster_versions'][-1]['status']=='draft'


def test_owner_can_save_reviewed_configuration_and_unconfirmed_cannot_generate():
    db=store()
    ctx=AuthCtx(token='fixture',client=db,profile=Profile(id='owner1',role='OWNER',facility_id='f1'))
    app.dependency_overrides[get_ctx]=lambda:ctx
    try:
        http=TestClient(app)
        response=http.post('/facility-configs',json={'config_key':'roster_analysis','config_json':profile()})
        assert response.status_code==201,response.text
        saved=response.json()
        assert saved['version']==2 and saved['active'] is True and saved['facility_id']=='f1'
        frozen=roster_analysis.freeze(db,'f1',saved['id'],db.data['roster_periods'][0])
        assert frozen['version']==2 and len(frozen['digest'])==64
        db.data['facility_json_configs'][-1]['config_json']['status']='proposed'
        with pytest.raises(ValueError,match='manager confirmation'):
            roster_analysis.freeze(db,'f1',saved['id'],db.data['roster_periods'][0])
    finally:app.dependency_overrides.clear()


def test_api_authorizes_profile_and_selected_version_before_export(monkeypatch):
    db=store()
    ctx=AuthCtx(token='fixture',client=db,profile=Profile(id='owner1',role='OWNER',facility_id='f1'))
    app.dependency_overrides[get_ctx]=lambda:ctx
    monkeypatch.setattr(router,'get_service_client',lambda:db)
    try:
        http=TestClient(app)
        body={'facility_id':'forged','period_id':'p1','source_version_id':'mv1','analysis_config_id':'cfg1','plan_mode':'C','solver_limits':{'max_seconds':2,'workers':1}}
        response=http.post('/optimize-roster?sync=true',json=body)
        assert response.status_code==200,response.text
        version=response.json()['roster_options'][0]['roster_version_id']
        result=http.get('/exports/naac/tahduty.xlsx',params={'period_id':'p1','version_id':version})
        assert result.status_code==200,result.text
        assert 'DRAFT' in result.headers['content-disposition']
        assert load_workbook(BytesIO(result.content)).sheetnames==list(roster_analysis.SHEETS)
        assert http.get('/exports/naac/tahduty.xlsx',params={'period_id':'p1','version_id':'foreign'}).status_code>=400
        db.data['facility_json_configs'][0]['facility_id']='f2'
        assert http.post('/optimize-roster?sync=true',json=body).status_code==422
        ctx.profile.role='FRONTLINE'
        assert http.post('/optimize-roster?sync=true',json=body).status_code==403
        assert http.post('/facility-configs',json={'config_key':'roster_analysis','config_json':profile()}).status_code==403
    finally:
        app.dependency_overrides.clear()
