"""Pure, closed-schema validation for synthetic export planning manifests.

No file loading, rendering, application imports, or I/O. A successful result
means structural validity only, never export readiness, approval, or fidelity.
The generic schema can describe later templates; validate_naac_m3_17 pins the
current Founder-confirmed inventory independently of caller-supplied metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
import re


NAAC_SHEET_NAMES = (
    "更期代號註解", "代號及時數(old)", "代號及時數", "覆診地點代號",
    *(f"TAHDuty(week{week})" for week in range(1, 7)),
    "TAHDuty(hours)", "TAHDuty(PH&dayoff)", "TAHDuty(DO更次數)",
    "TAHDuty(AP更)", "TAHDuty(C更男女)", "TAHDuty(N更男女)",
    "TAHDuty(用膳代號)",
)
NAAC_SHEET_IDS = (
    "annotations", "legacy_codes", "current_codes", "escort_locations",
    *(f"week_{week}" for week in range(1, 7)),
    "hours", "ph_dayoff", "supervisor", "ap_distribution",
    "sleepover_gender", "night_gender", "meal_codes",
)
# Symbolic references only: no renderer implementation is imported or invoked.
LAYOUTS = {
    "reference_table": frozenset({"naac_reference"}),
    "weekly_roster": frozenset({"naac_weekly"}),
    "staff_summary": frozenset({"naac_summary"}),
}
SAFETY = {
    "macros": "forbidden", "external_links": "forbidden",
    "external_connections": "forbidden", "copied_formulas": "forbidden",
    "untrusted_text": "literal_string",
}


class ManifestError(ValueError):
    """Invalid or unsupported manifest; messages contain paths, not input data."""


@dataclass(frozen=True)
class ValidationResult:
    sheet_count: int
    unresolved: tuple[str, ...]
    flagged: tuple[str, ...]


def _require(condition: bool, path: str, message: str) -> None:
    if not condition:
        raise ManifestError(f"{path}: {message}")


def _object(value: object, keys: set[str], path: str) -> dict:
    _require(type(value) is dict, path, "expected object")
    _require(set(value) == keys, path, "missing or unsupported fields")
    return value


def _text(value: object, path: str, maximum: int = 200) -> str:
    _require(type(value) is str, path, "expected string")
    _require(0 < len(value) <= maximum and value == value.strip(),
             path, "expected bounded nonblank text without outer whitespace")
    _require(not any(ord(char) < 32 or ord(char) == 127 for char in value),
             path, "control characters are forbidden")
    _require(not value.startswith(("=", "+", "-", "@")),
             path, "formula-like metadata is forbidden")
    return value


def _identifier(value: object, path: str) -> str:
    text = _text(value, path, 80)
    _require(re.fullmatch(r"[a-z][a-z0-9_-]*", text) is not None,
             path, "expected symbolic identifier")
    return text


def _metadata(value: object, path: str, choices: tuple,
              unresolved: list[str]) -> object:
    item = _object(value, {"status", "value"}, path)
    _require(type(item["status"]) is str and
             item["status"] in ("unresolved", "confirmed"),
             path, "expected unresolved or confirmed status")
    if item["status"] == "unresolved":
        _require(item["value"] is None, path, "unresolved value must be null")
        unresolved.append(path)
    else:
        _require(any(type(item["value"]) is type(choice) and
                     item["value"] == choice for choice in choices),
                 path, "unsupported confirmed value")
    return item["value"]


def validate_manifest(manifest: object) -> ValidationResult:
    """Validate an already-decoded object without modifying it.

    Unknown fields are rejected at every level. Formula and conditional-rule
    specifications must stay empty in this first slice; their future schema
    requires a separate reviewed change. No setting grants tenant authority.
    """
    root = _object(manifest, {"schema_version", "template_id", "template_version",
        "data_classification", "source", "cycle", "sheet_count", "safety", "sheets"}, "manifest")
    _require(type(root["schema_version"]) is int and root["schema_version"] == 1,
             "schema_version", "unsupported schema version")
    _identifier(root["template_id"], "template_id")
    _identifier(root["template_version"], "template_version")
    _require(root["data_classification"] == "synthetic_only",
             "data_classification", "synthetic_only is required")
    source = _object(root["source"], {"authority", "evidence", "operational_content_loaded"}, "source")
    _require(source["authority"] == "founder_confirmed_structure" and
             source["evidence"] == "approved_structural_documentation" and
             source["operational_content_loaded"] is False,
             "source", "only structural documentation is supported")
    cycle = _object(root["cycle"], {"days", "weeks", "timezone", "first_weekday"}, "cycle")
    _require(type(cycle["days"]) is int and cycle["days"] == 42 and
             type(cycle["weeks"]) is int and cycle["weeks"] == 6 and
             cycle["timezone"] == "Asia/Hong_Kong", "cycle", "expected six-week Hong Kong cycle")
    unresolved: list[str] = []
    flagged: list[str] = []
    _metadata(cycle["first_weekday"], "cycle.first_weekday", tuple(range(1, 8)), unresolved)
    safety = _object(root["safety"], set(SAFETY), "safety")
    _require(safety == SAFETY, "safety", "unsupported safety policy")
    sheets = root["sheets"]
    _require(type(sheets) is list and 0 < len(sheets) <= 64,
             "sheets", "expected 1 to 64 sheet specifications")
    _require(type(root["sheet_count"]) is int and root["sheet_count"] == len(sheets),
             "sheet_count", "must equal sheet list length")
    ids: set[str] = set()
    names: set[str] = set()
    weeks: list[int] = []
    for index, value in enumerate(sheets, 1):
        path = f"sheets[{index - 1}]"
        sheet = _object(value, {"id", "name", "order", "purpose", "renderer", "layout_id",
            "week_index", "visibility", "print", "layout_status", "calculation_status",
            "formula_specs", "conditional_rules"}, path)
        sid = _identifier(sheet["id"], f"{path}.id")
        name = _text(sheet["name"], f"{path}.name", 31)
        _require(not any(char in name for char in "[]:*?/\\") and
                 not name.startswith("'") and not name.endswith("'"),
                 f"{path}.name", "invalid Excel sheet name")
        _require(sid not in ids and name.casefold() not in names,
                 path, "duplicate sheet ID or name")
        ids.add(sid)
        names.add(name.casefold())
        _require(type(sheet["order"]) is int and sheet["order"] == index,
                 f"{path}.order", "must match contiguous list order")
        _text(sheet["purpose"], f"{path}.purpose")
        renderer = _identifier(sheet["renderer"], f"{path}.renderer")
        layout = _identifier(sheet["layout_id"], f"{path}.layout_id")
        _require(renderer in LAYOUTS and layout in LAYOUTS[renderer],
                 path, "unknown renderer or incompatible layout reference")
        if renderer == "weekly_roster":
            _require(type(sheet["week_index"]) is int and 1 <= sheet["week_index"] <= 6,
                     f"{path}.week_index", "expected week 1 to 6")
            weeks.append(sheet["week_index"])
        else:
            _require(sheet["week_index"] is None, f"{path}.week_index", "nonweekly sheet requires null")
        visibility = _metadata(sheet["visibility"], f"{path}.visibility",
                               ("visible", "hidden", "veryHidden"), unresolved)
        if visibility in ("hidden", "veryHidden"):
            flagged.append(f"{path}.visibility")
        printing = _object(sheet["print"], {"included_by_default", "profile_status"}, f"{path}.print")
        _metadata(printing["included_by_default"], f"{path}.print.included_by_default",
                  (True, False), unresolved)
        # Profiles, geometry and calculations are not defined by this slice.
        for label, status in (("print.profile_status", printing["profile_status"]),
                              ("layout_status", sheet["layout_status"]),
                              ("calculation_status", sheet["calculation_status"])):
            _require(status == "unresolved", f"{path}.{label}", "must remain unresolved in schema v1")
            unresolved.append(f"{path}.{label}")
        for field in ("formula_specs", "conditional_rules"):
            _require(type(sheet[field]) is list and not sheet[field],
                     f"{path}.{field}", "unsupported in schema v1; requires reviewed specification")
    _require(not weeks or weeks == list(range(1, 7)),
             "sheets.week_index", "weekly sheets must cover weeks 1 to 6 once, in order")
    return ValidationResult(len(sheets), tuple(unresolved), tuple(flagged))


def validate_naac_m3_17(manifest: object) -> ValidationResult:
    """Enforce the current inventory, even if a caller changes its template ID."""
    result = validate_manifest(manifest)
    _require(manifest["template_id"] == "naac-m3-17", "template_id", "expected naac-m3-17")
    sheets = manifest["sheets"]
    _require(tuple(s["name"] for s in sheets) == NAAC_SHEET_NAMES and
             tuple(s["id"] for s in sheets) == NAAC_SHEET_IDS,
             "sheets", "expected exact Founder-confirmed 17-sheet inventory and order")
    for index, sheet in enumerate(sheets):
        expected = "weekly_roster" if 4 <= index <= 9 else (
            "staff_summary" if 10 <= index <= 15 else "reference_table")
        _require(sheet["renderer"] == expected, f"sheets[{index}].renderer", "incorrect sheet role")
    return result
