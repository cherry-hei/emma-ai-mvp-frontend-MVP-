"""The vocabulary the care homes actually write in their roster spreadsheets.

Every entry here was taken from the source workbooks rather than invented: the
duty codes and their clock times come from the legend rows the homes print above
each roster, and the leave codes from the abbreviation line at the top of each
sheet. Nothing in this module touches the database - it is the dictionary the
cell grammar (`cells.py`) and the layout readers (`home_a.py`, `home_b.py`)
share, and the one place to edit when a home adds a code.

Two homes, two dialects
-----------------------
Home A rosters a 28-day cycle on two sheets (nurses/health workers, then care
workers) and writes task codes into the duty itself - ``A3`` is "A shift doing
task A3", ``A2N`` is "the A/N split shift whose morning half is task A2". Home B
rosters a natural month on one sheet, writes 12-hour ``7A``/``7P`` duties, and
carries floor and duty notes on a second row underneath each staff member.

The same code can mean different hours in different homes, and even on different
sheets of the same home (Home A's ``B`` is 08:00-16:00 for a nurse and
09:00-17:00 for a care worker). ``ShiftWindow`` therefore belongs to a
``SheetProfile``, not to a global table, and the importer writes the resolved
times onto each ``shifts`` row - which is why the schema keeps start/end on the
shift and not only on ``shift_definitions``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── cell markers ─────────────────────────────────────────────────────────────
# The homes cross-reference a duty cell to that day's event row with a symbol.
# They carry no scheduling meaning on their own; the layout reader resolves them
# against the events row and the importer records the link.
EVENT_MARKERS = ("▲", "*", "#", "※")

# Prefix meaning "this cell exists because the staff member asked for it" - the
# 員工要求 / staff-request layer the leave rules (Phase 5.5) price against a
# monthly quota. Home B tracks the same thing as a per-day request quota row.
REQUEST_PREFIX = "SR"


# ── duty codes ───────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ShiftWindow:
    """One duty code's clock time, as printed in the sheet's own legend."""

    code: str
    label: str
    start: str | None = None
    end: str | None = None
    # Two disjoint duty windows (the A/N split shift, or an A+P double duty).
    # Interpreted by emma_core.shifttime exactly like shift_definitions.segments.
    segments: tuple[dict[str, str], ...] = ()
    is_working: bool = True
    # Fairness/cost weight where a home counts a duty differently from its clock
    # hours. paid_minutes stays the pay truth.
    weighting_factor: float = 1.0

    @property
    def cross_midnight(self) -> bool:
        if self.segments:
            last = self.segments[-1]
            return last["end"] <= last["start"]
        if not (self.start and self.end):
            return False
        return self.end <= self.start


# ── leave / non-duty codes ───────────────────────────────────────────────────
@dataclass(frozen=True)
class LeaveCode:
    """A non-duty cell: rest, statutory holiday, or a leave type.

    ``category`` is the ``leave_requests.category`` the row belongs to, so an
    imported cell lands in the same approval queue a staff-app request would.
    ``shift_code`` is the non-working shift type written into the roster grid, so
    the cell still renders where the home wrote it.
    """

    code: str
    label: str
    label_zh: str | None = None
    category: str = "al"          # al|duty|sick - matches leave_requests.category
    shift_code: str = "AL"        # non-working shift_definitions.shift_type
    consumes_balance: bool = False
    # Statutory/public holidays are entitlements, not requests: they are recorded
    # on the roster but must not queue for approval.
    is_leave_request: bool = True


def _leave(code, label, label_zh=None, *, category="al", shift_code=None,
           consumes_balance=False, is_leave_request=True) -> LeaveCode:
    return LeaveCode(code=code, label=label, label_zh=label_zh, category=category,
                     shift_code=shift_code or code, consumes_balance=consumes_balance,
                     is_leave_request=is_leave_request)


# Keyed by canonical code. The aliases each home writes map in below.
LEAVE_CODES: dict[str, LeaveCode] = {
    # rest and compensation - rostered, never a leave request
    "OFF":   _leave("OFF", "Rest day", "休息日", category="duty", is_leave_request=False),
    "DO":    _leave("DO", "Day off", "例假", category="duty", is_leave_request=False),
    "CL":    _leave("CL", "Compensatory rest", "補休", category="duty",
                    consumes_balance=True),
    "CO":    _leave("CO", "Compensatory day off", "補假", category="duty",
                    consumes_balance=True),
    "SLEEP": _leave("SLEEP", "Sleeping day", "夜更後補睡", category="duty",
                    is_leave_request=False),
    "ND":    _leave("ND", "No-duty day", "無工作日", category="duty",
                    is_leave_request=False),
    # statutory entitlements - rostered, not requested
    "SH":    _leave("SH", "Statutory holiday", "法定假日", category="duty",
                    is_leave_request=False),
    "PH":    _leave("PH", "Public holiday", "公眾假期", category="duty",
                    is_leave_request=False),
    # leave proper
    "AL":    _leave("AL", "Annual leave", "年假", consumes_balance=True),
    "VL":    _leave("VL", "Vacation leave", "大假", consumes_balance=True),
    "SL":    _leave("SL", "Sick leave", "病假", category="sick"),
    "DSL":   _leave("DSL", "Compassionate sick leave", "恩恤病假", category="sick"),
    "FAL":   _leave("FAL", "Family care leave", "關顧假"),
    "BL":    _leave("BL", "Bonus leave", "獎勵假"),
    "MAL":   _leave("MAL", "Marriage leave", "婚假"),
    "MTL":   _leave("MTL", "Maternity leave", "產假"),
    "COL":   _leave("COL", "Compassionate leave", "恩恤假"),
    "LSL":   _leave("LSL", "Long-service leave", "長期服務假"),
    "NPL":   _leave("NPL", "No-pay leave", "無薪假"),
    "VACL":  _leave("VACL", "Vaccination leave", "疫苗假"),
    "FL":    _leave("FL", "Festival leave", "節令假"),
    "CIVIC": _leave("CIVIC", "Civic duty leave", "公民參與假"),
    "TRN":   _leave("TRN", "Training / course", "培訓", category="duty",
                    is_leave_request=False),
}

# Every spelling the two homes use, normalised (upper-cased, punctuation and
# whitespace stripped) -> canonical code. Chinese forms are matched as written.
LEAVE_ALIASES: dict[str, str] = {
    # rest / compensation
    "休": "OFF", "休息": "OFF", "休息日": "OFF",
    "DO": "DO", "例假": "DO",
    "補休": "CL", "補": "CL", "CL": "CL", "補假": "CO", "補DO": "CO", "CO": "CO",
    "S": "SLEEP", "SLEEP": "SLEEP", "SD": "SLEEP",
    "ND": "ND", "無工作日": "ND",
    # statutory
    "法": "SH", "法假": "SH", "法定假日": "SH", "SH": "SH",
    "公": "PH", "公假": "PH", "公眾假期": "PH", "PH": "PH",
    # leave
    "年": "AL", "年假": "AL", "AL": "AL",
    "大": "VL", "大假": "VL", "VL": "VL",
    "病": "SL", "病假": "SL", "SL": "SL",
    "DSL": "DSL", "恩恤病假": "DSL",
    "FAL": "FAL", "關顧假": "FAL",
    "BL": "BL", "獎勵假": "BL", "生日假": "BL",
    "MAL": "MAL", "婚假": "MAL",
    "MTL": "MTL", "產": "MTL", "產假": "MTL",
    "COL": "COL", "ML": "COL", "恩恤假": "COL",
    "LSL": "LSL", "長期服務假": "LSL",
    "NPL": "NPL", "無薪假": "NPL",
    "VACL": "VACL", "VACL1": "VACL", "VACL2": "VACL", "VACL3": "VACL", "疫苗假": "VACL",
    "FL": "FL", "節令": "FL", "節": "FL",
    "民": "CIVIC", "公民參與假": "CIVIC",
    # 救 is the homes' shorthand for first-aid / rescue training; 導向學習 and the
    # external-training T land in the same bucket.
    "救": "TRN", "T": "TRN", "STDL": "TRN", "進修假期": "TRN", "導向學習": "TRN",
}


# ── ranks ────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RankSpec:
    """A rank label as written in the sheet, resolved to schema values.

    ``staff_rank`` and ``employment_type`` are database enums, so a home's local
    wording ("HW I" for an imported-labour health worker, "外判" for an
    outsourced care worker) resolves here rather than leaking into queries.
    """

    rank: str
    employment_type: str = "local_ft"
    label: str | None = None
    is_relief_pool: bool = False   # a row whose cells hold relief workers' names


RANK_ALIASES: dict[str, RankSpec] = {
    # nurses
    "SRN":  RankSpec("RN", label="Senior registered nurse"),
    "RN":   RankSpec("RN"),
    "EN":   RankSpec("EN"),
    "AS":   RankSpec("RN", label="Assistant superintendent (RN)"),
    # health workers / care workers
    "HW":   RankSpec("HW"),
    "HWI":  RankSpec("HW", "imported_labor", "Health worker (imported labour)"),
    "HCA":  RankSpec("HCA"),
    "HCAI": RankSpec("HCA", "imported_labor", "Health-care assistant (imported labour)"),
    "CW":   RankSpec("CW"),
    "RCW":  RankSpec("CW", label="Residential care worker"),
    "PCW":  RankSpec("PCW"),
    "AW":   RankSpec("AW"),
    "LN":   RankSpec("HCA", label="Long-night care staff"),
    # therapy / support
    "PTA":  RankSpec("PTA"),
    "OTA":  RankSpec("OTA"),
    # external workforce
    "外判":   RankSpec("HCA", "outsource", "Outsourced care staff"),
    "替假":   RankSpec("HCA", "casual", "Relief pool", is_relief_pool=True),
    "RUNNER": RankSpec("HCA", label="Floor runner"),
}

# "PT ..." marks a part-time contract in both homes; the rank follows.
PART_TIME_PREFIXES = ("PT", "P/T", "兼職")


def resolve_rank(label: str) -> RankSpec | None:
    """'PT HW' -> HW on a local part-time contract; 'HW I' -> imported labour."""
    cleaned = "".join(ch for ch in label.upper() if ch.isalnum() or ch in "/一二三")
    part_time = False
    for prefix in PART_TIME_PREFIXES:
        key = prefix.replace("/", "")
        if cleaned.startswith(key) and cleaned != key:
            cleaned = cleaned[len(key):]
            part_time = True
            break
    # Trailing digits are the home's row numbering ("RCW12", "HW3"), not rank.
    cleaned = cleaned.rstrip("0123456789").replace("/", "")
    spec = RANK_ALIASES.get(cleaned)
    if not spec:
        return None
    if part_time and spec.employment_type == "local_ft":
        return RankSpec(spec.rank, "local_pt", f"{spec.label or spec.rank} (part-time)")
    return spec


# ── per-sheet duty dictionaries ──────────────────────────────────────────────
def _win(code, label, start=None, end=None, **kw) -> ShiftWindow:
    return ShiftWindow(code=code, label=label, start=start, end=end, **kw)


# Home A · 護士及保健員 sheet legend:
#   A 07:00-15:00 · B 08:00-16:00 · E/E2/E3 09:00-17:00 · P 13:30-21:30
#   A/N 07:00-13:30 and 21:30-07:00 (next day) · AS: B 08:00-16:48, D 09:00-17:48
_HOME_A_NURSING: tuple[ShiftWindow, ...] = (
    _win("A", "Morning (A)", "07:00", "15:00"),
    _win("B", "Morning B", "08:00", "16:00"),
    _win("E", "Morning E", "09:00", "17:00"),
    _win("D", "Day (assistant superintendent)", "09:00", "17:48"),
    _win("P", "Afternoon (P)", "13:30", "21:30"),
    _win("N", "Night (N)", "21:30", "07:00"),
    _win("AN", "A/N split", "07:00", "13:30", segments=(
        {"start": "07:00", "end": "13:30"}, {"start": "21:30", "end": "07:00"})),
)

# Home A · RCW 院舍護理員 sheet legend - B, D and E differ from the nursing sheet,
# and the care workers additionally run 長A / 長P long duties.
_HOME_A_CARE: tuple[ShiftWindow, ...] = (
    _win("A", "Morning (A)", "07:00", "15:00"),
    _win("B", "Morning B", "09:00", "17:00"),
    _win("D", "Day (D)", "09:30", "17:30"),
    _win("E", "Evening (E)", "13:00", "21:00"),
    _win("P", "Afternoon (P)", "13:30", "21:30"),
    _win("LA", "Long A (長A)", "07:00", "15:30"),
    _win("LP", "Long P (長P)", "13:00", "21:30"),
    _win("N", "Night (N)", "21:30", "07:00"),
    _win("AN", "A/N split", "07:00", "13:30", segments=(
        {"start": "07:00", "end": "13:30"}, {"start": "21:30", "end": "07:00"})),
)

# Home B · one legend for the whole sheet:
#   D 09:00-18:00 · A 07:00-16:00 · P 12:30-21:30 · N 21:15-07:15
#   A/N 07:00-14:30 (30 min meal) and 21:15-07:15 · 7A 07:00-19:00 · 7P 19:00-07:00
#   9A 09:00-21:00 · 9P 21:00-09:00
_HOME_B: tuple[ShiftWindow, ...] = (
    _win("A", "Morning (A)", "07:00", "16:00"),
    _win("P", "Afternoon (P)", "12:30", "21:30"),
    _win("D", "Day (D)", "09:00", "18:00"),
    _win("N", "Night (N)", "21:15", "07:15"),
    _win("AN", "A/N split", "07:00", "14:30", segments=(
        {"start": "07:00", "end": "14:30"}, {"start": "21:15", "end": "07:15"})),
    _win("7A", "12h day (7A)", "07:00", "19:00", weighting_factor=1.5),
    _win("7P", "12h night (7P)", "19:00", "07:00", weighting_factor=1.5),
    _win("9A", "9A (09:00-21:00)", "09:00", "21:00", weighting_factor=1.5),
    _win("9P", "9P (21:00-09:00)", "21:00", "09:00", weighting_factor=1.5),
)

# A double duty ("A3 + P3", "A1 OT / P2") is two disjoint windows in one day -
# the same shape as the A/N split shift, so it is stored the same way.
_DOUBLE_DUTY = _win("AP", "A+P double duty", weighting_factor=2.0)

# Cells where the home wrote clock times instead of a code ("09:30-19:00",
# "8-4"). The hours are real and belong on the roster; only the label is ad hoc.
_AD_HOC = _win("AH", "Ad-hoc hours")

# Written forms of a duty code -> canonical code, applied before task-digit and
# marker stripping.
SHIFT_ALIASES: dict[str, str] = {
    "A/N": "AN", "AN": "AN", "A-N": "AN",
    "長A": "LA", "長P": "LP", "LONGA": "LA", "LONGP": "LP",
    "E2": "E", "E3": "E",
    "RUNA": "A", "RUNP": "P",     # Home B relief runner on an A/P duty
}


# ── sub-row duty notes (Home B) ──────────────────────────────────────────────
# Home B writes the floor and the standing duty for each cell on a second row
# underneath the staff member. These are task labels, not duty codes.
SUBROW_TASKS: dict[str, str] = {
    "R": "Runner",
    "C": "Canteen",
    "AA": "Assist exercise",
    "DRUG": "Drug round",
    "LDD": "Late drug round",
    "A/V": "Audio-visual duty",
    "OUTING": "Resident outing",
    "TALK": "Talk attendant",
}
# Floor tokens the sub-row uses; '6/F+C' is "6/F, canteen duty".
FLOOR_TOKENS = ("1/F", "2/F", "6/F", "3/F", "4/F", "5/F", "G/F")


# ── facility profiles ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class SheetProfile:
    """One roster sheet's duty dictionary plus the rank group it belongs to."""

    name: str
    windows: tuple[ShiftWindow, ...]
    note: str = ""

    def window(self, code: str) -> ShiftWindow | None:
        return self._by_code.get(code)

    @property
    def _by_code(self) -> dict[str, ShiftWindow]:
        return {w.code: w for w in self.windows}


@dataclass(frozen=True)
class FacilityProfile:
    """What a home looks like, as read from its own roster workbook."""

    code: str                       # facilities.code - 'A' or 'B'
    name: str
    cycle_type: str                 # roster_periods.cycle_type
    scheduling_cycle_days: int
    sheets: tuple[SheetProfile, ...]
    units: tuple[tuple[str, str, str], ...] = ()   # (unit_type, name, code)
    double_duty: ShiftWindow = _DOUBLE_DUTY
    ad_hoc: ShiftWindow = _AD_HOC
    task_prefixes: tuple[str, ...] = ("A", "P", "N")
    notes: tuple[str, ...] = field(default_factory=tuple)

    def sheet(self, name: str) -> SheetProfile:
        for s in self.sheets:
            if s.name == name:
                return s
        return self.sheets[0]

    @property
    def shift_windows(self) -> tuple[ShiftWindow, ...]:
        """Facility-wide duty dictionary for `shift_definitions`.

        Where two sheets disagree on a code's hours the first sheet wins and the
        difference is carried on each `shifts` row instead - see the module
        docstring.
        """
        seen: dict[str, ShiftWindow] = {}
        for sheet in self.sheets:
            for window in sheet.windows:
                seen.setdefault(window.code, window)
        for extra in (self.double_duty, self.ad_hoc):
            seen.setdefault(extra.code, extra)
        return tuple(seen.values())


HOME_A = FacilityProfile(
    code="A",
    name="Care Home A (救世軍式)",
    cycle_type="28day",
    scheduling_cycle_days=28,
    sheets=(
        SheetProfile("nursing", _HOME_A_NURSING, "護士及保健員 - RN / EN / HW / AS"),
        SheetProfile("care", _HOME_A_CARE, "院舍護理員 - RCW, incl. 長A / 長P"),
    ),
    units=(("wing", "East Wing", "EW"), ("wing", "West Wing", "WW")),
    notes=("Task codes are written into the duty: A3 = A shift task A3, "
           "A2N = A/N split whose morning half is task A2.",),
)

HOME_B = FacilityProfile(
    code="B",
    name="Care Home B (多層院舍)",
    cycle_type="natural_month",
    scheduling_cycle_days=31,
    sheets=(SheetProfile("floors", _HOME_B, "1/F, 2/F, 6/F combined sheet"),),
    units=(("floor", "1/F", "1F"), ("floor", "2/F", "2F"), ("floor", "6/F", "6F")),
    notes=("Floor and standing duty are written on a second row under each "
           "staff member.",),
)

PROFILES: dict[str, FacilityProfile] = {"A": HOME_A, "B": HOME_B}
