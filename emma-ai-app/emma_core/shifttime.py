"""The single definition of what a shift's clock times mean.

Most shifts are one contiguous block, but the Code of Practice A/N shift is a
**split shift**: per the scheduling spec, Home A works 07:00–13:30 *and* 21:30–07:00
the next day; Home B works 07:00–14:30 *and* 21:15–07:15. Two disjoint duty
windows, with an unpaid rest gap between them.

Representing that as one 07:00→13:30-next-day span gets three separate things
wrong, and each consumer needs a different answer:

    paid_minutes()   hours / OT / fairness   -> the SUM of the segments (16h),
                                                not the 30.5h elapsed envelope
    envelope()       overlap / rest checks   -> the OUTER span, because the staff
                                                member is unavailable across all of it
    duty_spans()     ratio coverage          -> EACH segment separately, so an A/N
                                                nurse is not counted as present
                                                during their afternoon rest

`segments` (jsonb on shift_definitions/shifts) is the source of truth when set;
a row without it is a single contiguous shift and behaves exactly as before.
"""
from __future__ import annotations

from collections.abc import Mapping

# (start_min, end_min, crosses_midnight)
Segment = tuple[int, int, bool]


def to_minutes(hhmm: str | None) -> int | None:
    """'HH:MM[:SS]' -> minutes from midnight; None passes through."""
    if not hhmm:
        return None
    parts = str(hhmm).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def segment_length(start: int, end: int, cross: bool) -> int:
    return (1440 - start) + end if (cross or end <= start) else end - start


def duty_segments(shift: Mapping) -> tuple[Segment, ...]:
    """The windows the staff member is actually on duty."""
    raw = shift.get("segments")
    if raw:
        out: list[Segment] = []
        for seg in raw:
            start, end = to_minutes(seg.get("start")), to_minutes(seg.get("end"))
            if start is None or end is None:
                continue
            out.append((start, end, end <= start))
        if out:
            return tuple(out)

    start, end = to_minutes(shift.get("start_time")), to_minutes(shift.get("end_time"))
    if start is None or end is None:
        return ()
    return ((start, end, bool(shift.get("cross_midnight")) or end <= start),)


def paid_minutes(shift: Mapping) -> int:
    """Paid duty minutes. An explicit `paid_minutes` wins (a facility may pay a
    handover or a sleep-in differently from the clock); otherwise it is the sum
    of the duty segments."""
    explicit = shift.get("paid_minutes")
    if explicit is not None:
        return int(explicit)
    return sum(segment_length(*seg) for seg in duty_segments(shift))


def envelope(shift: Mapping) -> Segment | None:
    """Outer (start, end, crosses) span covering every segment - what overlap and
    minimum-rest checks must use, since the whole span is unavailable."""
    segs = duty_segments(shift)
    if not segs:
        return None
    if len(segs) == 1:
        return segs[0]
    start = segs[0][0]
    # walk to the last segment's end, tracking whether we ran past midnight
    crossed = False
    for s, e, c in segs:
        if c or (s < start and not crossed):
            crossed = True
    last_end = segs[-1][1]
    return (start, last_end, crossed or last_end <= start)


def day_spans(start: int, end: int, cross: bool) -> list[tuple[int, int]]:
    """Split a possibly midnight-wrapping window into same-day [a, b) intervals."""
    if cross or end <= start:
        spans = [(start, 1440)]
        if end > 0:
            spans.append((0, end))
        return spans
    return [(start, end)]


def duty_spans(shift: Mapping) -> list[tuple[int, int]]:
    """Every same-day on-duty interval, segments expanded - the coverage footprint."""
    out: list[tuple[int, int]] = []
    for start, end, cross in duty_segments(shift):
        out.extend(day_spans(start, end, cross))
    return out


def covers_window(shift: Mapping, win_start: int, win_end: int) -> bool:
    """Does any duty segment overlap the statutory window?"""
    win_cross = win_end <= win_start
    for a, b in duty_spans(shift):
        for c, d in day_spans(win_start, win_end, win_cross):
            if a < d and c < b:
                return True
    return False
