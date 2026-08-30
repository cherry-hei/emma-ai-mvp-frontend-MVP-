@echo off
rem ── Emma AI dev launcher (monorepo) ──────────────────────────────────
rem Runs the backend (emma-ai-app, FastAPI) and the frontend (Next.js, at
rem the repo root) together. Run from the repo root:  dev.cmd
rem   Backend  -> http://localhost:8000  (docs at /docs)
rem   Frontend -> http://localhost:3001
setlocal
set "ROOT=%~dp0"

rem Node lives in Program Files, but a terminal opened before Node was installed
rem still carries the old PATH and can't see npm. Patch it in for this window
rem (and for the child window `start` spawns below) instead of failing.
where npm >nul 2>nul || (
  if exist "%ProgramFiles%\nodejs\npm.cmd" (
    echo [dev] npm not on PATH, using "%ProgramFiles%\nodejs"
    set "PATH=%ProgramFiles%\nodejs;%PATH%"
  )
)
where npm >nul 2>nul || (
  echo [dev] ERROR: npm not found. Install Node.js LTS, then open a new terminal.
  exit /b 1
)

rem Cap the dev server heap. Without this, `next dev` sets --max-old-space-size
rem to 50%% of system RAM (~24 GB here), so V8 lets garbage pile up for ~30 min
rem until it dies with "Ineffective mark-compacts near heap limit". An explicit
rem value is respected by next-dev and makes V8 collect at a sane threshold.
set "NODE_OPTIONS=--max-old-space-size=4096"

rem `dev.cmd clean` wipes the Turbopack dev cache (.next grows to 500 MB+).
if /i "%~1"=="clean" (
  echo [dev] Clearing .next cache...
  if exist "%ROOT%.next" rmdir /s /q "%ROOT%.next"
)

if not exist "%ROOT%node_modules" (
  echo [dev] Installing frontend deps ^(first run only, may take a minute^)...
  pushd "%ROOT%" && call npm install && popd
)

@REM echo [dev] Backend  -^> http://localhost:8000  ^(docs /docs^)
echo [dev] Frontend -^> http://localhost:3001
@REM start "emma-api" cmd /k "cd /d "%ROOT%emma-ai-app" && uvicorn api.main:app --reload"
start "emma-web" cmd /k "cd /d "%ROOT%" && npm run dev:next"
endlocal
