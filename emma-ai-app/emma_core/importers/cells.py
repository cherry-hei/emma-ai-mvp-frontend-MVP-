"""The grammar of one roster cell.

A cell in a care-home roster is not a single code. ``▲SR A5 + OT x 3 hrs`` says
five separate things: this day is linked to the meeting marked ▲, the staff
member asked for it, the duty is the A shift doing task A5, and three hours of
overtime were worked. ``DSL AM / 1-5 PM`` says the morning was compassionate
sick leave and the afternoon was worked 13:00-17:00.

``parse_cell`` turns that text into a :class:`CellIntent` the loader can write
without re-reading the string, and reports whatever it could not resolve so the
import's validation summary can name the exact source cell instead of silently
dropping it.

The grammar, in the order it is applied:

1. **Normalise** - collapse whitespace, fold full-width punctuation, and repair
   the handful of typing slips present in the source files (``o.5`` for ``0.5``,
   ``=`` and ``_`` written where ``+`` was meant, ``補'休``).
2. **Markers** - ``▲ * # ※`` are cross-references to that day's event row. They
   are lifted out wherever they appear, which also rescues ``A#/N#`` into the
   plain ``A/N`` split duty.
3. **Request prefix** - a leading ``SR`` means the staff member requested this
   cell (the 員工要求 layer the Phase 5.5 quota rules price).
4. **Split** - on ``/ + , &`` and parentheses, and at any ASCII↔CJK boundary, so
   ``B節4`` separates into the B duty and four hours of festival leave while
   ``補DO`` (a known code) stays whole.
5. **Classify** each fragment as a duty, a leave code, an hour adjustment, an
   explicit time window, a part-day qualifier, or a note.
6. **Assemble** - a lone quantified ``CL`` becomes the day's leave; two duties
   become one double-duty shift with two segments.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .vocab import (
    EVENT_MARKERS, LEAVE_ALIASES, LEAVE_CODES, REQUEST_PREFIX, SHIFT_ALIASES,
    FacilityProfile, LeaveCode, SheetProfile, ShiftWindow,
)

# Codes whose trailing number is a running count ("DO1" is the first rest day of
# the cycle), not a number of hours.
_COUNTER_CODES = frozenset({"DO", "CO", "OFF", "VACL"})

# Duty codes, longest base first so 長A wins over A and 7A over 7.
_DUTY_BASES = ("長A", "長P", "A/N", "7A", "7P", "9A", "9P", "LA", "LP", "AN",
               "A", "B", "D", "E", "P", "N")
_DUTY_RE = re.compile(
    r"^(?P<base>" + "|".join(re.escape(b) for b in _DUTY_BASES) + r")"
    r"(?P<task>\d{1,2})?(?P<night>N)?$"
)
# The task-code series a duty draws from: a long-A or a 12-hour 7A duty still
# carries an A-series task ('長A7' is the long A shift doing task A7).
_TASK_SERIES = {"LA": "A", "7A": "A", "9A": "A", "LP": "P", "7P": "P", "9P": "P"}

_TIME_RE = re.compile(r"^(?P<h1>\d{1,2}):(?P<m1>\d{2})-(?P<h2>\d{1,2}):(?P<m2>\d{2})$")
# "9A-1P" - hour with an am/pm letter on each side.
_MERIDIEM_RANGE_RE = re.compile(r"^(?P<h1>\d{1,2})(?P<p1>[AP])-(?P<h2>\d{1,2})(?P<p2>[AP])$")
# "8-4", "7-11", "10-7", "1-5 PM" - bare hours, optionally with one meridiem for
# the whole range; otherwise a smaller end hour means the afternoon.
_HOUR_RANGE_RE = re.compile(r"^(?P<h1>\d{1,2})-(?P<h2>\d{1,2})(?P<half>[AP]M?)?$")
# "0830-1630" - a 24-hour time written without its colon.
_COMPACT_RANGE_RE = re.compile(r"^(?P<t1>\d{3,4})-(?P<t2>\d{3,4})$")
_QUANTIFIED_RE = re.compile(r"^(?P<code>[A-Z]+|[一-鿿]+)(?P<qty>\d+(?:\.\d+)?)$")
# '2/F', '6/F' written into a duty cell scope that day to a floor. The slash is
# folded away before splitting (see _split), so both spellings are accepted.
_FLOOR_RE = re.compile(r"^(?P<digit>\d)\s*/?\s*F$", re.I)

# "OT x 3 hrs", "CL 0.5 hr", "CL x 20 mins", "OT" (quantity omitted in the source)
_ADJUST_RE = re.compile(
    r"^(?P<code>OT|CL|CO)\s*(?:X\s*)?(?P<qty>\d+(?:\.\d+)?)?\s*"
    r"(?P<unit>HRS?|HOURS?|MINS?|MINUTES?)?$"
)

_DAY_PARTS = {"AM": "AM", "PM": "PM", "上午": "AM", "下午": "PM"}

# Fragments that carry no scheduling meaning on their own.
_IGNORED = frozenset({"", "-", "–", "—", "+", "X"})


@dataclass(frozen=True)
class Duty:
    """One duty window resolved against the sheet's legend."""

    shift_code: str                 # canonical shift_definitions.shift_type
    task_code: str | None = None    # 'A3', 'P2', 'N3' - the home's task-code layer
    start: str | None = None
    end: str | None = None
    segments: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class CellIntent:
    """Everything one roster cell asserts about one staff member on one day."""

    raw: str
    duties: tuple[Duty, ...] = ()
    leave: LeaveCode | None = None
    leave_hours: float | None = None
    leave_sequence: int | None = None      # 'DO3' - third rest day of the cycle
    is_request: bool = False
    event_markers: tuple[str, ...] = ()
    ot_minutes: int = 0
    cl_minutes: int = 0
    day_part: str | None = None
    time_windows: tuple[tuple[str, str], ...] = ()
    unit_hint: str | None = None           # '2/F P' - the floor this duty covers
    notes: tuple[str, ...] = field(default_factory=tuple)
    unparsed: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.duties or self.leave or self.time_windows
                    or self.notes or self.unparsed)

    @property
    def is_working(self) -> bool:
        return bool(self.duties) or bool(self.time_windows and not self.leave)

    @property
    def task_codes(self) -> tuple[str, ...]:
        return tuple(d.task_code for d in self.duties if d.task_code)


# ── normalisation ────────────────────────────────────────────────────────────
_FOLD = {
    "＋": "+", "／": "/", "，": ",", "（": "(", "）": ")", "：": ":",
    "－": "-", "–": "-", "—": "-", "、": ",", "'": "", "’": "", "　": " ",
}
# Typing slips present in the source workbooks. Each is a literal fix, not a
# guess: '=' and '_' appear where every sibling cell writes '+', and 'o.5' is a
# letter o typed for a zero.
_TYPOS = (
    (re.compile(r"(?<=\d)\s*=\s*(?=OT|CL)", re.I), " + "),
    (re.compile(r"\s+_\s+(?=OT|CL)", re.I), " + "),
    (re.compile(r"\bO(\.\d+)", re.I), r"0\1"),
    # '1,6/F' is shorthand for two floors, not a decimal.
    (re.compile(r"(\d)\s*,\s*(\d)(?=/F)", re.I), r"\1/F \2"),
)


def normalise(raw: object) -> str:
    """Cell value -> comparable text. Empty for anything blank."""
    if raw is None:
        return ""
    text = str(raw)
    for src, dst in _FOLD.items():
        text = text.replace(src, dst)
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in _TYPOS:
        text = pattern.sub(replacement, text)
    return text


def _strip_markers(text: str) -> tuple[str, tuple[str, ...]]:
    found = tuple(m for m in EVENT_MARKERS if m in text)
    for marker in EVENT_MARKERS:
        text = text.replace(marker, " ")
    return re.sub(r"\s+", " ", text).strip(" /+,&"), found


def _strip_request(text: str) -> tuple[str, bool]:
    """A leading 'SR' marks a staff request.

    ``\\b`` is no help here: the homes write ``SR補休`` with no separator, and CJK
    counts as a word character, so the boundary is expressed as "SR not followed
    by another letter" - which also leaves Home B's ``SRN`` rank alone.
    """
    match = re.match(rf"^{REQUEST_PREFIX}(?![A-Za-z])[\s/+]*", text, re.I)
    if not match:
        return text, False
    return text[match.end():].strip(), True


def _split(text: str) -> list[str]:
    """Break a cell into fragments without severing known compound codes."""
    # Fold the codes the splitting below would otherwise cut in half: 'A/N' and
    # '2/F' contain the delimiter, and '長A7' straddles the CJK/ASCII boundary that
    # separates 'B節4' into a duty and a leave code.
    guarded = re.sub(r"\bA\s*/\s*N\b", "AN", text, flags=re.I)
    guarded = re.sub(r"(\d)\s*/\s*F\b", r"\1F", guarded, flags=re.I)
    guarded = re.sub(r"長\s*([AP])", r"L\1", guarded)
    parts = re.split(r"[/+,&()]", guarded)
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 'B節4' -> 'B', '節4'. Digits stay with the code they quantify, and a
        # mixed-script code ('補DO') is matched whole before any splitting.
        if part.upper().replace(" ", "") in LEAVE_ALIASES or part in LEAVE_ALIASES:
            out.append(part)
            continue
        out.extend(p for p in re.split(r"(?<=[一-鿿])(?=[A-Za-z])"
                                      r"|(?<=[A-Za-z0-9])(?=[一-鿿])", part) if p)
    return [p.strip() for p in out if p.strip()]


# ── fragment classification ──────────────────────────────────────────────────
def _hhmm(hour: int, minute: int = 0) -> str:
    return f"{hour % 24:02d}:{minute:02d}"


def _as_time_window(fragment: str) -> tuple[str, str] | None:
    upper = fragment.upper().replace(" ", "")
    if m := _TIME_RE.match(upper):
        return (_hhmm(int(m["h1"]), int(m["m1"])), _hhmm(int(m["h2"]), int(m["m2"])))
    if m := _MERIDIEM_RANGE_RE.match(upper):
        h1, h2 = int(m["h1"]), int(m["h2"])
        if m["p1"] == "P" and h1 < 12:
            h1 += 12
        if m["p2"] == "P" and h2 < 12:
            h2 += 12
        return (_hhmm(h1), _hhmm(h2))
    if m := _COMPACT_RANGE_RE.match(upper):
        parts = []
        for token in (m["t1"], m["t2"]):
            hour, minute = int(token[:-2]), int(token[-2:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            parts.append(_hhmm(hour, minute))
        return (parts[0], parts[1])
    if m := _HOUR_RANGE_RE.match(upper):
        h1, h2 = int(m["h1"]), int(m["h2"])
        if not (0 <= h1 <= 23 and 0 <= h2 <= 23):
            return None
        if m["half"] and m["half"].startswith("P"):
            # '1-5 PM' is 13:00-17:00.
            h1 += 12 if h1 < 12 else 0
            h2 += 12 if h2 < 12 else 0
        elif h2 < h1 and h2 + 12 <= 23:
            # '8-4' is 08:00-16:00; '7-11' stays in the morning.
            h2 += 12
        return (_hhmm(h1), _hhmm(h2))
    return None


def _as_adjustment(fragment: str) -> tuple[str, int | None] | None:
    """'OT x 3 hrs' -> ('OT', 180). Quantity None when the source omitted it."""
    upper = fragment.upper().replace(".", ".").strip()
    m = _ADJUST_RE.match(upper)
    if not m:
        # 'CL8', 'CL8.5', '+CL4' - the quantity is glued to the code.
        q = _QUANTIFIED_RE.match(upper)
        if q and q["code"] in {"OT", "CL", "CO"}:
            return (q["code"], int(round(float(q["qty"]) * 60)))
        return None
    if m["qty"] is None:
        return (m["code"], None)
    qty = float(m["qty"])
    unit = (m["unit"] or "HRS").upper()
    minutes = int(round(qty)) if unit.startswith("MIN") else int(round(qty * 60))
    return (m["code"], minutes)


def _as_leave(fragment: str) -> tuple[LeaveCode, float | None] | None:
    key = fragment.upper().replace(" ", "")
    if code := LEAVE_ALIASES.get(key) or LEAVE_ALIASES.get(fragment):
        return (LEAVE_CODES[code], None)
    if m := _QUANTIFIED_RE.match(key):
        if code := LEAVE_ALIASES.get(m["code"]):
            return (LEAVE_CODES[code], float(m["qty"]))
    return None


def _as_duty(fragment: str, sheet: SheetProfile,
             profile: FacilityProfile) -> Duty | None:
    key = fragment.upper().replace(" ", "")
    canonical = SHIFT_ALIASES.get(key) or SHIFT_ALIASES.get(fragment)
    if canonical:
        window = sheet.window(canonical)
        return _duty_from(window, None) if window else None

    match = _DUTY_RE.match(fragment.replace(" ", "")) or _DUTY_RE.match(key)
    if not match:
        return None
    base = SHIFT_ALIASES.get(match["base"].upper(), match["base"])
    base = SHIFT_ALIASES.get(base, base)
    task_digits, is_night = match["task"], bool(match["night"])
    # 'A2N' is the A/N split shift carrying morning task A2.
    task_prefix = _TASK_SERIES.get(base, base)
    if is_night:
        if base not in ("A", "LA"):
            return None
        base = "AN"
    window = sheet.window(base)
    if not window:
        return None
    task_code = f"{task_prefix}{task_digits}" if task_digits else None
    if task_code and task_prefix not in profile.task_prefixes:
        task_code = None
    return _duty_from(window, task_code)


def _duty_from(window: ShiftWindow, task_code: str | None) -> Duty:
    return Duty(shift_code=window.code, task_code=task_code,
                start=window.start, end=window.end, segments=window.segments)


# ── the parser ───────────────────────────────────────────────────────────────
def parse_cell(raw: object, profile: FacilityProfile,
               sheet: SheetProfile | None = None) -> CellIntent:
    """Parse one roster cell against a facility's duty dictionary."""
    text = normalise(raw)
    if not text:
        return CellIntent(raw="")
    sheet = sheet or profile.sheets[0]

    body, markers = _strip_markers(text)
    body, is_request = _strip_request(body)

    duties: list[Duty] = []
    leaves: list[tuple[LeaveCode, float | None]] = []
    adjustments: list[tuple[str, int | None]] = []
    windows: list[tuple[str, str]] = []
    notes: list[str] = []
    unparsed: list[str] = []
    day_part: str | None = None
    unit_hint: str | None = None

    fragments = _split(body)
    while fragments:
        fragment = fragments.pop(0)
        if fragment.upper() in _IGNORED:
            continue
        if part := _DAY_PARTS.get(fragment.upper()) or _DAY_PARTS.get(fragment):
            day_part = day_part or part
            continue
        if m := _FLOOR_RE.match(fragment.replace(" ", "")):
            unit_hint = unit_hint or f'{m["digit"]}/F'
            continue
        if window := _as_time_window(fragment):
            windows.append(window)
            continue
        if adjustment := _as_adjustment(fragment):
            adjustments.append(adjustment)
            continue
        if leave := _as_leave(fragment):
            leaves.append(leave)
            continue
        if duty := _as_duty(fragment, sheet, profile):
            duties.append(duty)
            continue
        # Space-separated compounds ('A3 OT', '2/F P', 'DSL AM') are only split
        # once the fragment failed as a whole, so 'Run A' and 'CL x 8 hrs' - which
        # do match whole - keep their spaces.
        words = fragment.split()
        if len(words) > 1:
            fragments = words + fragments
            continue
        # Free text the homes add for context ("早返", "Nurse M.") is kept as a
        # note; anything else is surfaced for a human to look at.
        if re.search(r"[一-鿿]", fragment) or len(fragment) > 3:
            notes.append(fragment)
        else:
            unparsed.append(fragment)

    ot_minutes = sum(m for code, m in adjustments if code == "OT" and m)
    cl_minutes = sum(m for code, m in adjustments if code in ("CL", "CO") and m)
    if any(m is None for _, m in adjustments):
        notes.append("overtime / compensatory hours not stated in source")

    # A cell that is nothing but compensatory hours is a compensatory day, not an
    # adjustment to a duty that was never rostered.
    if not duties and not leaves:
        compensatory = next(
            ((c, m) for c, m in adjustments if c in ("CL", "CO")), None)
        if compensatory:
            code, minutes = compensatory
            leaves.append((LEAVE_CODES[code],
                           round(minutes / 60, 2) if minutes else None))
            cl_minutes = 0

    leave, leave_hours, leave_sequence = None, None, None
    if leaves:
        leave, quantity = leaves[0]
        if quantity is not None:
            if leave.code in _COUNTER_CODES:
                leave_sequence = int(quantity)
            else:
                leave_hours = quantity
        for extra, _ in leaves[1:]:
            notes.append(f"also marked {extra.code}")

    duties = _merge_duties(duties, windows, leave, profile)
    return CellIntent(
        raw=text, duties=tuple(duties), leave=leave, leave_hours=leave_hours,
        leave_sequence=leave_sequence, is_request=is_request,
        event_markers=markers, ot_minutes=ot_minutes, cl_minutes=cl_minutes,
        day_part=day_part, time_windows=tuple(windows), unit_hint=unit_hint,
        notes=tuple(dict.fromkeys(notes)), unparsed=tuple(unparsed),
    )


def _merge_duties(duties: list[Duty], windows: list[tuple[str, str]],
                  leave: LeaveCode | None, profile: FacilityProfile) -> list[Duty]:
    """Resolve the duties a cell asserts into the shifts to write.

    Two duties in one cell ("A3 + P3", "A1 OT / P2") are two disjoint windows on
    the same day - structurally identical to the A/N split shift, so they are
    stored the same way rather than as two competing cells. A cell that gives only
    clock times ("09:30-19:00", "8-4") is a real duty the home wrote outside its
    own dictionary, so it becomes an ad-hoc shift rather than being dropped.
    """
    if len(duties) == 1 and windows and not duties[0].segments:
        # An explicit time window overrides the legend's hours for that day.
        start, end = windows[0]
        duties = [Duty(duties[0].shift_code, duties[0].task_code, start, end)]
    if not duties and windows and not leave:
        ad_hoc = profile.ad_hoc
        duties = [Duty(ad_hoc.code, None, windows[0][0], windows[0][1])]
    if len(duties) < 2:
        return duties
    segments = tuple(
        {"start": d.start, "end": d.end}
        for d in duties if d.start and d.end
    )
    tasks = "+".join(d.task_code for d in duties if d.task_code)
    combined = profile.double_duty
    return [Duty(
        shift_code=combined.code, task_code=tasks or None,
        start=segments[0]["start"] if segments else None,
        end=segments[-1]["end"] if segments else None,
        segments=segments,
    )]


# ── Home B's second row ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class SubRowNote:
    """Floor and standing duty written under a Home B staff member's duty cell."""

    floor: str | None = None
    tasks: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    raw: str = ""


def parse_subrow(raw: object) -> SubRowNote:
    """'6/F+C' -> 6/F, canteen duty. '2/F 7-7' -> 2/F on the 12-hour pattern."""
    from .vocab import FLOOR_TOKENS, SUBROW_TASKS

    text = normalise(raw)
    if not text:
        return SubRowNote()
    floor, tasks, notes = None, [], []
    for fragment in re.split(r"[+,\s]+", text):
        if not fragment:
            continue
        upper = fragment.upper()
        matched_floor = next((f for f in FLOOR_TOKENS if upper.startswith(f)), None)
        if matched_floor:
            floor = floor or matched_floor
            remainder = upper[len(matched_floor):].strip()
            if remainder:
                notes.append(remainder)
            continue
        if task := SUBROW_TASKS.get(upper):
            tasks.append(task)
            continue
        notes.append(fragment)
    return SubRowNote(floor=floor, tasks=tuple(dict.fromkeys(tasks)),
                      notes=tuple(dict.fromkeys(notes)), raw=text)
