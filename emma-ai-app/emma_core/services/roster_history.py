"""Read-only roster history scoped to one facility and period/version."""
from __future__ import annotations

import csv
import io
import json


def scope_versions(client, facility_id: str, period_id: str, version_id: str | None = None):
    periods = (client.table('roster_periods').select('*')
               .eq('facility_id', facility_id).eq('id', period_id).execute().data)
    if not periods:
        raise ValueError('roster period not found')
    query = (client.table('roster_versions').select('*')
             .eq('facility_id', facility_id).eq('period_id', period_id))
    if version_id:
        query = query.eq('id', version_id)
    versions = query.execute().data or []
    if version_id and not versions:
        raise ValueError('roster version not found in this period')
    return periods[0], versions


def _references_version(row: dict, ids: set[str]) -> bool:
    for key in ('before_json', 'after_json'):
        value = row.get(key)
        if isinstance(value, dict) and str(value.get('roster_version_id') or '') in ids:
            return True
    return row.get('entity_table') == 'roster_versions' and str(row.get('entity_id') or '') in ids


def read_history(client, facility_id: str, period_id: str, version_id: str | None,
                 *, include_audit: bool, limit: int = 200):
    _, versions = scope_versions(client, facility_id, period_id, version_id)
    ids = {str(row['id']) for row in versions}
    events = []
    changes = []
    truncated = False
    if ids:
        events = (client.table('roster_publish_events').select('*')
                  .eq('facility_id', facility_id).in_('roster_version_id', sorted(ids))
                  .order('created_at', desc=True).limit(limit + 1).execute().data or [])
        truncated = len(events) > limit
        events = events[:limit]
        if include_audit:
            # Bound the scan and expose truncation instead of pretending it is a
            # complete audit export. Never include shared/null-facility rows.
            rows = (client.table('audit_logs').select('*').eq('facility_id', facility_id)
                    .order('created_at', desc=True).limit(10001).execute().data or [])
            truncated = truncated or len(rows) > 10000
            matches = [row for row in rows[:10000] if _references_version(row, ids)]
            truncated = truncated or len(matches) > limit
            changes = [{key: row.get(key) for key in (
                'id', 'action', 'entity_table', 'entity_id', 'created_at',
                'before_json', 'after_json', 'reason',
            )} for row in matches[:limit]]
    return {'period_id': period_id, 'version_id': version_id,
            'can_read_audit': include_audit, 'changes': changes,
            'publish_events': events, 'truncated': truncated}


def csv_cell(value):
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (dict, list)) else str(value or '')
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def audit_csv(history: dict) -> str:
    if history['truncated']:
        raise ValueError('Audit export exceeds the safe row limit; narrow the roster version filter.')
    output = io.StringIO()
    writer = csv.writer(output, lineterminator='\n')
    keys = ('id', 'created_at', 'action', 'entity_table', 'entity_id', 'before_json', 'after_json', 'reason')
    writer.writerow(keys)
    for row in history['changes']:
        writer.writerow([csv_cell(row.get(key)) for key in keys])
    return '\ufeff' + output.getvalue()
