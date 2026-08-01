"""/notifications/stream - Server-Sent Events for the manager dashboard (spec SA.4).

The acceptance criterion is "manager receives update within 5 seconds". SSE over
a short poll of `notifications` meets that with no broker, which is the same
trade the architecture record makes for the solver: a job table plus polling
beats a message bus the team also has to operate.

Why not WebSockets: the traffic is one-directional (server tells the dashboard
something changed) and SSE reconnects by itself. A WebSocket would add a
handshake, a heartbeat protocol and a reconnect loop we would have to write.

The stream is deliberately finite. Each connection runs for `max_seconds` and
then closes; `EventSource` reconnects on its own with the cursor it last saw. A
never-ending generator would pin a threadpool worker per manager for the life of
the process, and nothing would ever reclaim one whose client vanished.
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.deps import AuthCtx, get_ctx
from emma_core.services import notifications as notify
from emma_core.services._common import now_iso

router = APIRouter(tags=["notifications"])

# Under the 5-second acceptance criterion with room for a slow query.
_POLL_SECONDS = 2.0


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


@router.get("/notifications/stream")
def stream(after: str | None = Query(default=None,
                                     description="ISO timestamp cursor; defaults to now"),
           max_seconds: float = Query(default=25.0, ge=0, le=300),
           ctx: AuthCtx = Depends(get_ctx)):
    """Replay everything addressed to this profile since `after`, then poll.

    Scoped to the caller's own `profile_id`, so this is not a facility firehose:
    a manager sees the events fanned out to them by `push_to_approvers`, which
    already applied the permission matrix when it chose recipients.
    """
    cursor = after or now_iso()

    def events() -> Iterator[str]:
        nonlocal cursor
        deadline = time.monotonic() + max_seconds
        # `cursor` is echoed first so a reconnecting client can confirm the
        # server understood its position rather than guessing after silence.
        yield _sse("cursor", {"cursor": cursor})
        while True:
            rows = notify.since(ctx.client, ctx.facility_id, after_iso=cursor,
                                profile_id=ctx.profile_id)
            for row in rows:
                yield _sse("notification", row)
                cursor = str(row["created_at"])
            if time.monotonic() >= deadline:
                break
            # A comment line keeps proxies from closing an idle connection.
            yield ": keep-alive\n\n"
            time.sleep(min(_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
        yield _sse("reconnect", {"cursor": cursor})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # nginx buffers text/event-stream by default, which turns a live
            # stream into one delivery at close.
            "X-Accel-Buffering": "no",
        },
    )
