"""Turn a deterministic result into something safe to hand an outside model.

Identities become per-request aliases, free text is dropped, and `assert_clean`
is the last gate before anything leaves. The gate is deliberately paranoid: it
re-reads the finished payload rather than trusting that the walk above it did
its job.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Aliased, so the model gets a stable token instead of a real identifier.
IDENTITY_KEYS: dict[str, str] = {
    "id": "REF",
    "staff_id": "STAFF",
    "candidate_staff_id": "STAFF",
    "offered_staff_id": "STAFF",
    "replacement_staff_id": "STAFF",
    "absent_staff_id": "STAFF",
    "actor_staff_id": "STAFF",
    "profile_id": "USER",
    "offered_by": "USER",
    "approved_by": "USER",
    "actor_profile_id": "USER",
    "unit_id": "UNIT",
    "primary_unit_id": "UNIT",
    "shift_id": "SHIFT",
    "incident_id": "INCIDENT",
    "facility_id": "HOME",
    "roster_version_id": "ROSTER",
}

# Removed outright. A name buys the model nothing that its alias does not.
DROP_KEYS = frozenset({
    "name", "name_en", "unit_name", "email", "phone", "mobile", "telephone",
    "hkid", "id_number", "identity_number", "date_of_birth", "dob", "address",
    "emergency_contact", "auth_user_id", "photo_url", "avatar_url",
})

# Typed by a person, so it can hold anything at all.
FREE_TEXT_KEYS = frozenset({
    "note", "notes", "reason", "remark", "remarks", "response_note",
    "description", "comment", "comments", "message",
})

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
HKID = re.compile(r"\b[A-Z]{1,2}\d{6}\(?[0-9A]\)?\b")
HK_PHONE = re.compile(r"(?<!\d)[23569]\d{7}(?!\d)")
CJK = re.compile(r"[㐀-鿿豈-﫿]")

SCANS = (("email", EMAIL), ("hkid", HKID), ("phone", HK_PHONE))


class LeakError(RuntimeError):
    """Something identifiable reached the last gate before a provider call."""

    def __init__(self, kind: str, sample: str) -> None:
        super().__init__(f"outbound payload still contains {kind}: {sample!r}")
        self.kind, self.sample = kind, sample


@dataclass
class AliasMap:
    """One request's two-way map between real identifiers and their aliases."""

    forward: dict[str, str] = field(default_factory=dict)
    reverse: dict[str, str] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)

    def alias(self, kind: str, value: Any) -> str:
        key = str(value)
        if key in self.forward:
            return self.forward[key]
        self._counts[kind] = self._counts.get(kind, 0) + 1
        token = f"{kind}_{self._counts[kind]}"
        self.forward[key], self.reverse[token] = token, key
        return token

    def real(self, token: str) -> str | None:
        return self.reverse.get(token)

    def secrets(self) -> tuple[str, ...]:
        return tuple(self.forward)


def _scrub_text(text: str, names: Iterable[str]) -> str:
    """Redact a free-text field instead of dropping it."""
    out = text
    # Longest first, so "陳大文" is not half-consumed by a shorter match.
    for name in sorted({n for n in names if n and len(n) > 1}, key=len, reverse=True):
        out = out.replace(name, "[redacted]")
    out = EMAIL.sub("[redacted]", out)
    out = HKID.sub("[redacted]", out)
    out = HK_PHONE.sub("[redacted]", out)
    return CJK.sub("", out).strip()


def anonymise(value: Any, aliases: AliasMap | None = None, *,
              free_text: str = "drop", names: Iterable[str] = ()) -> tuple[Any, AliasMap]:
    """Rewrite a structure so no identity survives in it.

    `free_text="drop"` removes person-written fields entirely; `"redact"` keeps
    them with the names and contact patterns taken out.
    """
    aliases = aliases if aliases is not None else AliasMap()

    def walk(node: Any, key: str | None) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in DROP_KEYS:
                    continue
                if k in FREE_TEXT_KEYS:
                    if free_text != "redact" or not isinstance(v, str):
                        continue
                    cleaned = _scrub_text(v, names)
                    if cleaned:
                        out[k] = cleaned
                    continue
                out[k] = walk(v, k)
            return out
        if isinstance(node, (list, tuple)):
            return [walk(v, key) for v in node]
        if key in IDENTITY_KEYS and node is not None:
            return aliases.alias(IDENTITY_KEYS[key], node)
        return node

    return walk(value, None), aliases


def assert_clean(payload: Any, *, secrets: Iterable[str] = (),
                 allow_cjk: bool = False) -> None:
    """Refuse to let a payload leave if anything identifiable is still in it."""
    blob = payload if isinstance(payload, str) else json.dumps(
        payload, ensure_ascii=False, default=str)

    for secret in secrets:
        text = str(secret or "")
        # Chinese names are short; the CJK scan below is what catches those.
        if len(text) >= 3 and text in blob:
            raise LeakError("a known identifier", text)

    for kind, pattern in SCANS:
        hit = pattern.search(blob)
        if hit:
            raise LeakError(kind, hit.group(0))

    if not allow_cjk:
        hit = CJK.search(blob)
        if hit:
            raise LeakError("Chinese text", blob[max(0, hit.start() - 20):hit.end() + 20])


def collect_secrets(rows: Iterable[dict]) -> tuple[str, ...]:
    """Every value from the source rows that must not appear downstream."""
    found: set[str] = set()
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        for key in DROP_KEYS:
            value = row.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "-":
                found.add(value.strip())
    return tuple(found)
