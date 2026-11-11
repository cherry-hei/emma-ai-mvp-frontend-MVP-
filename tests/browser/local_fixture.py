"""Local-only synthetic browser verification; never shipped or deployed."""
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'emma-ai-app'))
os.environ.update(APP_ENV='test',SUPABASE_URL='http://127.0.0.1:54321',SUPABASE_ANON_KEY='',SUPABASE_SERVICE_ROLE_KEY='',CORS_ORIGINS='http://127.0.0.1:3017',BEDROCK_ENABLED='false')
from fastapi.responses import JSONResponse
from api.main import app
from api.deps import AuthCtx,get_ctx
from api.routers import optimize as router
from emma_core.models import Profile
from tests.test_roster_analysis_integration import store
db=store()
db.data['facilities'][0].update(name='Invented browser test home')
db.data['roster_periods'][0]['status']='draft'
db.data['roster_versions'][0].update(label='Empty manual test period',version_type='manual')
db.data['roster_versions'][0].pop('created_at',None)
for s in db.data['staff']:s['employment_type']='local_ft'
for s in db.data['shift_definitions']:s['label']=s['shift_type']
ctx=AuthCtx(token='local-synthetic-test-token',client=db,profile=Profile(id='owner1',email='owner@example.invalid',role='OWNER',facility_id='f1'))
app.dependency_overrides[get_ctx]=lambda:ctx
router.get_service_client=lambda:db
@app.middleware('http')
async def fake_identity(request,call_next):
    headers={'Access-Control-Allow-Origin':'http://127.0.0.1:3017','Access-Control-Allow-Credentials':'true'}
    if request.url.path=='/auth/login' and request.method=='POST':
        return JSONResponse({'access_token':'local-synthetic-test-token','token_type':'bearer','user_id':'owner1','email':'owner@example.invalid','role':'OWNER','facility_id':'f1','facility_name':'Invented browser test home'},headers=headers)
    if request.url.path=='/auth/me' and request.method=='GET':
        return JSONResponse({**ctx.profile.model_dump(mode='json'),'facility':{'id':'f1','name':'Invented browser test home'}},headers=headers)
    return await call_next(request)
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=8017)
