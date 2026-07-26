@echo off
rem ── Emma AI dev launcher ─────────────────────────────────────────────
rem Runs the backend (this repo, FastAPI) and the frontend (main-branch
rem worktree, Next.js) together. Run from the repo root:  dev.cmd
rem   Backend  -> http://localhost:8000  (docs at /docs)
rem   Frontend -> http://localhost:3001
setlocal
set "ROOT=%~dp0"
set "FRONTEND=%ROOT%..\emma-ai-frontend"

if not exist "%FRONTEND%\package.json" (
  echo [dev] Frontend worktree missing at %FRONTEND%
  echo [dev] Create it once:  git worktree add "%FRONTEND%" main
  exit /b 1
)

if not exist "%FRONTEND%\node_modules" (
  echo [dev] Installing frontend deps ^(first run only, may take a minute^)...
  pushd "%FRONTEND%" && call npm install && popd
)

echo [dev] Backend  -^> http://localhost:8000  ^(docs /docs^)
echo [dev] Frontend -^> http://localhost:3001
start "emma-api" cmd /k "cd /d "%ROOT%emma-ai-app" && uvicorn api.main:app --reload"
start "emma-web" cmd /k "cd /d "%FRONTEND%" && npm run dev"
endlocal
