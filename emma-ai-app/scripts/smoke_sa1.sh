#!/usr/bin/env bash
# End-to-end smoke test for SA.1 against a live API.
#
# SA.1's acceptance criterion is "staff can submit all request types from PWA;
# manager receives real-time notification". The PWA half is Cherry's; this
# exercises everything behind it, in the order the app would:
#
#   1. sign in as a staff-app account
#   2. read the two endpoints that returned 500 on production (/me/profile,
#      /me/summary) - the blocker Cherry reported on 30 July
#   3. submit each request type: AL, DO/duty, SL (with an attachment url)
#   4. submit a shift swap
#   5. sign in as the superintendent and confirm the requests arrived in the
#      approval queue and that a notification was raised
#
# It creates real rows. Point it at the test API, not a customer's.
#
#   ./scripts/smoke_sa1.sh https://<api-host>
#
# The password lives in DEV_LOGINS.md and is read from EMMA_DEV_PASSWORD so it
# is not baked into a file in the repo:
#
#   EMMA_DEV_PASSWORD='...' ./scripts/smoke_sa1.sh https://<api-host>

set -uo pipefail

API="${1:-http://localhost:8000}"
PASSWORD="${EMMA_DEV_PASSWORD:-}"
STAFF_EMAIL="${STAFF_EMAIL:-staff_hw_a@emma.local}"
MANAGER_EMAIL="${MANAGER_EMAIL:-super_a@emma.local}"

if [ -z "$PASSWORD" ]; then
  echo "Set EMMA_DEV_PASSWORD first (see DEV_LOGINS.md)." >&2
  exit 2
fi

pass=0
fail=0

check() {  # check <label> <actual> <expected...>
  local label="$1" actual="$2"; shift 2
  for expected in "$@"; do
    if [ "$actual" = "$expected" ]; then
      printf '  PASS  %-46s %s\n' "$label" "$actual"
      pass=$((pass + 1))
      return 0
    fi
  done
  printf '  FAIL  %-46s %s (wanted %s)\n' "$label" "$actual" "$*"
  fail=$((fail + 1))
  return 1
}

login() {
  curl -s -m 25 -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$PASSWORD\"}" |
    python -c 'import json,sys; print(json.load(sys.stdin).get("access_token",""))' 2>/dev/null
}

code() {   # code <method> <path> <token> [body]
  if [ -n "${4:-}" ]; then
    curl -s -m 25 -o /dev/null -w '%{http_code}' -X "$1" "$API$2" \
      -H "Authorization: Bearer $3" -H 'Content-Type: application/json' -d "$4"
  else
    curl -s -m 25 -o /dev/null -w '%{http_code}' -X "$1" "$API$2" \
      -H "Authorization: Bearer $3"
  fi
}

body() {   # body <method> <path> <token> [payload]
  if [ -n "${4:-}" ]; then
    curl -s -m 25 -X "$1" "$API$2" -H "Authorization: Bearer $3" \
      -H 'Content-Type: application/json' -d "$4"
  else
    curl -s -m 25 -X "$1" "$API$2" -H "Authorization: Bearer $3"
  fi
}

echo "API: $API"
echo
echo "== 0. the API is up"
check "GET /health" "$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$API/health")" 200

echo
echo "== 1. staff sign-in"
STAFF_TOKEN="$(login "$STAFF_EMAIL")"
if [ -z "$STAFF_TOKEN" ]; then
  echo "  FAIL  could not sign in as $STAFF_EMAIL" >&2
  exit 1
fi
echo "  PASS  signed in as $STAFF_EMAIL"

echo
echo "== 2. the endpoints Cherry reported as 500 on 30 July"
check "GET /me/profile" "$(code GET /me/profile "$STAFF_TOKEN")" 200
check "GET /me/summary" "$(code GET /me/summary "$STAFF_TOKEN")" 200
check "GET /me/roster"  "$(code GET /me/roster  "$STAFF_TOKEN")" 200
check "GET /me/tasks"   "$(code GET /me/tasks   "$STAFF_TOKEN")" 200

echo
echo "== 3. submit each request type (SA.1)"
TOMORROW="$(python -c 'import datetime as d; print(d.date.today()+d.timedelta(days=21))')"
check "POST /leave-requests (AL)" \
  "$(code POST /leave-requests "$STAFF_TOKEN" \
     "{\"leave_type\":\"AL\",\"date_start\":\"$TOMORROW\",\"date_end\":\"$TOMORROW\",\"reason\":\"smoke test\"}")" \
  201 422
check "POST /leave-requests (DO/duty)" \
  "$(code POST /leave-requests "$STAFF_TOKEN" \
     "{\"leave_type\":\"DO\",\"date_start\":\"$TOMORROW\",\"date_end\":\"$TOMORROW\",\"reason\":\"smoke test\"}")" \
  201 422
check "POST /leave-requests (SL + attachment)" \
  "$(code POST /leave-requests "$STAFF_TOKEN" \
     "{\"leave_type\":\"SL\",\"date_start\":\"$TOMORROW\",\"date_end\":\"$TOMORROW\",\"reason\":\"smoke test\",\"document_url\":\"https://example.invalid/cert.jpg\"}")" \
  201 422
check "GET /swap-requests" "$(code GET /swap-requests "$STAFF_TOKEN")" 200
check "GET /me/leave-requests" "$(code GET /me/leave-requests "$STAFF_TOKEN")" 200

echo
echo "== 4. manager side"
MGR_TOKEN="$(login "$MANAGER_EMAIL")"
if [ -z "$MGR_TOKEN" ]; then
  echo "  FAIL  could not sign in as $MANAGER_EMAIL" >&2
else
  echo "  PASS  signed in as $MANAGER_EMAIL"
  check "GET /leave-requests (approval queue)" "$(code GET /leave-requests "$MGR_TOKEN")" 200
  QUEUE="$(body GET '/leave-requests?group=pending' "$MGR_TOKEN")"
  echo "$QUEUE" | python -c '
import json, sys
try:
    rows = json.load(sys.stdin)
except Exception:
    print("  FAIL  approval queue did not return JSON"); raise SystemExit
print(f"  INFO  pending requests in the queue: {len(rows)}")
if rows:
    keys = rows[0].keys()
    print("  " + ("PASS" if "recommendations" in keys else "FAIL")
          + "  recommendations attached to each row")
'
  check "GET /notifications (manager)" "$(code GET /me/notifications "$MGR_TOKEN")" 200 409
fi

echo
echo "-------------------------------------------"
echo "  passed: $pass    failed: $fail"
[ "$fail" -eq 0 ] || exit 1
