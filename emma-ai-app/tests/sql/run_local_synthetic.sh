#!/usr/bin/env bash
# Synthetic-only throwaway Postgres 16 check. Do not point at an external DB.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MIGRATION="$(realpath "$HERE/../../supabase/migrations/20261001000025_direct_messages.sql")"
TEST="$HERE/duty_window_messages_local.sql"
TEMP_DIR="$(mktemp -d /tmp/emma-synthetic-sql.XXXXXX)"
DB="emma_synthetic_oct01_${RANDOM}"
cleanup() {
    sudo -u postgres dropdb --if-exists "$DB" >/dev/null 2>&1 || true
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT
sudo pg_ctlcluster 16 main start >/dev/null 2>&1 || true
cp "$TEST" "$TEMP_DIR/test.sql"
cp "$MIGRATION" "$TEMP_DIR/migration.sql"
chmod 755 "$TEMP_DIR"
sed -i "s|$MIGRATION|$TEMP_DIR/migration.sql|g" "$TEMP_DIR/test.sql"
chmod 644 "$TEMP_DIR"/*.sql
sudo -u postgres createdb "$DB"
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$DB" -f "$TEMP_DIR/test.sql"
