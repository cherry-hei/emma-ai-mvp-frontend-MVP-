// Client-side mirrors of the server's task-eligibility rules, so a picker can
// only offer a task the API would accept.
//
// These live here rather than inside a component because two dialogs need them -
// the roster board's inline cell editor and CreateShiftModal - and two copies of
// a rule that must agree with the backend is one copy too many. The server is
// still the authority: it re-checks on every write and returns the reasons, and
// `RealRosterBoard` renders those. This only keeps the manager from being
// offered a choice that will be refused.

import type { RuleIssue, ShiftDef, TaskDefOut } from '@/lib/apiTypes'

export function toMinutes(hhmm?: string | null): number | null {
  if (!hhmm) return null
  const [h, m] = hhmm.slice(0, 5).split(':').map(Number)
  return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null
}

/**
 * Mirrors `shift_type_matches` on the server.
 *
 * A split shift (A/N) is two duty windows, so a morning code genuinely belongs
 * on that cell. Filtering it out of the picker would hide a duty the rules
 * accept - the manager would think it was forbidden rather than simply absent.
 */
export function shiftCovers(required: string | null | undefined, shiftType: string,
                            defs: ShiftDef[]): boolean {
  if (!required || required === shiftType) return true
  const actual = defs.find((d) => d.shift_type === shiftType)
  if (!actual?.segments?.length) return false
  const target = defs.find((d) => d.shift_type === required)
  const start = toMinutes(target?.start_time)
  const end = toMinutes(target?.end_time)
  if (start === null || end === null) return false
  return actual.segments.some((seg) => {
    const segStart = toMinutes(seg.start)
    if (segStart === null) return false
    // The window may wrap past midnight, in which case it is two spans.
    return end <= start
      ? segStart >= start || segStart < end
      : segStart >= start && segStart < end
  })
}

export function canSeeTask(actualRank: string, task: TaskDefOut, shiftType: string,
                           defs: ShiftDef[]): boolean {
  if (!shiftCovers(task.shift_type, shiftType, defs)) return false
  if (!task.required_rank || task.required_rank === actualRank) return true
  return new Set([actualRank, task.required_rank]).size === 2
    && [actualRank, task.required_rank].every((rank) => rank === 'CW' || rank === 'HCA')
}

export const taskLabel = (td: TaskDefOut) => td.task_name || td.task_code

/**
 * Turn one machine reason into something a manager can act on. Anything the UI
 * has no wording for still shows its reason code rather than being swallowed -
 * a silent rejection is worse than an ugly one.
 */
export function reasonText(issue: RuleIssue, isZH: boolean): string {
  switch (issue.reason) {
    case 'rank':
      return isZH
        ? `職級不符（需 ${issue.required}，實為 ${issue.actual}）`
        : `wrong rank — needs ${issue.required}, this is ${issue.actual}`
    case 'shift_type':
      return isZH
        ? `更別不符（此任務屬 ${issue.required} 更）`
        : `wrong shift — that code belongs to the ${issue.required} shift`
    case 'medication_audit':
      return isZH ? '未通過藥物審核' : 'not medication-audited'
    case 'unaudited_external':
      return isZH
        ? `未審核外援僅可做 ${issue.allowed_task_codes?.join(' / ')}`
        : `unaudited external staff may only do ${issue.allowed_task_codes?.join(' / ')}`
    case 'qualification_all_of':
      return isZH
        ? `缺少資格：${issue.missing?.join('、')}`
        : `missing qualification: ${issue.missing?.join(', ')}`
    case 'qualification_any_of':
      return isZH ? '缺少任一必要資格' : 'missing one of the required qualifications'
    case 'qualification_none_of':
      return isZH
        ? `資格互斥：${issue.blocked?.join('、')}`
        : `blocked by qualification: ${issue.blocked?.join(', ')}`
    case 'new_staff_restricted':
      return isZH ? '新入職員工需導師陪同' : 'new staff need a mentor for this duty'
    case 'unknown_task':
      return isZH ? '任務不在任務字典內' : 'not in the task dictionary'
    case 'unit':
    case 'shift_unit':
      return isZH ? '單位不符' : 'wrong unit'
    default:
      return issue.message || issue.reason || (isZH ? '不符合規則' : 'not allowed')
  }
}

/** Flatten the API's nested per-task issues into one readable line each. */
export function issueLines(issues: RuleIssue[], isZH: boolean): string[] {
  return issues.map((issue) => {
    const reasons = (issue.issues?.length ? issue.issues : [issue])
      .map((r) => reasonText(r, isZH)).join(' · ')
    return issue.task_label ? `${issue.task_label}: ${reasons}` : reasons
  })
}
