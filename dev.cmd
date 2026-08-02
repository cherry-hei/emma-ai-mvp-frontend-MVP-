@echo off
rem ── Emma AI dev launcher (monorepo) ──────────────────────────────────
rem Runs the backend (emma-ai-app, FastAPI) and the frontend (Next.js, at
rem the repo root) together. Run from the repo root:  dev.cmd
rem   Backend  -> http://localhost:8000  (docs at /docs)
rem   Frontend -> http://localhost:3001
setlocal
set "ROOT=%~dp0"

if not exist "%ROOT%node_modules" (
  echo [dev] Installing frontend deps ^(first run only, may take a minute^)...
  pushd "%ROOT%" && call npm install && popd
)

@REM echo [dev] Backend  -^> http://localhost:8000  ^(docs /docs^)
echo [dev] Frontend -^> http://localhost:3001
@REM start "emma-api" cmd /k "cd /d "%ROOT%emma-ai-app" && uvicorn api.main:app --reload"
start "emma-web" cmd /k "cd /d "%ROOT%" && npm run dev"
endlocal
