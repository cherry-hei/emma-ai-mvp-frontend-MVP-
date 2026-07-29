"""Domain errors that carry structured evidence to the API boundary.

Services raise plain `ValueError` for ordinary bad input; the API maps that to a
422 with a human message. Some rejections, though, are a *list of reasons* the
UI has to render one by one — the roster cell editor has to say "wrong rank"
and "not medication-audited" separately, not print one concatenated sentence.
Those raise `RuleViolationError` so the reasons survive as data.
"""
from __future__ import annotations


class RuleViolationError(ValueError):
    """A rejection that carries machine-readable reasons alongside its message.

    Subclasses `ValueError` so any handler that already treats service input
    errors as 422 keeps working if it does not know about this type.
    """

    code = "rule_violation"

    def __init__(self, message: str, issues: list[dict], **context) -> None:
        super().__init__(message)
        self.issues = issues
        self.context = context

    def payload(self) -> dict:
        return {"code": self.code, "message": str(self),
                "issues": self.issues, **self.context}


class TaskEligibilityError(RuleViolationError):
    """A task code may not be given to this staff member on this shift."""

    code = "task_not_eligible"
