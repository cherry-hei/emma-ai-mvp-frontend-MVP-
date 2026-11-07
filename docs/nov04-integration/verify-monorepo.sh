#!/usr/bin/env bash
set -euo pipefail
# Read-only/local validation after each app's frozen dependency install.
# No API calls, migrations, deployment, credentials or install/update steps.
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
printf '\n[1/5] Staff PWA strict typecheck\n'
pnpm --dir staff-pwa check
printf '\n[2/5] Staff PWA contract/session tests\n'
pnpm --dir staff-pwa test
printf '\n[3/5] Staff PWA production build\n'
pnpm --dir staff-pwa build
printf '\n[4/5] Manager UI regression\n'
npm run test:ui
printf '\n[5/5] Manager strict typecheck and build\n'
npm run build
printf '\nAll five local validation steps completed. This is not live RLS/UAT or deployment evidence.\n'
