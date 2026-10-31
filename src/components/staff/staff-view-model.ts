import type { ApiStaff } from '@/lib/apiTypes'

export type StaffDirectoryCard = {
  id: string
  primaryName: string
  secondaryName: string | null
  roleCode: string
  employmentType: string
  unitName: string | null
  status: string | null
  certificates: string[]
  scheduledHours: number | null
  contractedPeriodHours: number | null
}

function suppliedText(value: string | null | undefined): string | null {
  const text = value?.trim()
  return text ? text : null
}

/**
 * Keep the directory deliberately close to the tenant-scoped API row.  In
 * particular, absent contracts, units and certificates remain absent: the UI
 * must not substitute the old prototype's defaults or a sample staff record.
 */
export function toStaffDirectoryCard(staff: ApiStaff): StaffDirectoryCard {
  const englishName = suppliedText(staff.name_en)
  const localName = suppliedText(staff.name)
  const primaryName = englishName ?? localName ?? staff.id
  const secondaryName = englishName && localName && englishName !== localName ? localName : null
  const certificates = [
    ...staff.certs,
    ...staff.certificates.map((certificate) => certificate.cert_type),
  ].map(suppliedText).filter((certificate): certificate is string => Boolean(certificate))

  return {
    id: staff.id,
    primaryName,
    secondaryName,
    roleCode: staff.rank,
    employmentType: staff.employment_type,
    unitName: suppliedText(staff.unit_name),
    status: suppliedText(staff.status),
    certificates: Array.from(new Set(certificates)),
    // Zero is a returned value, not a missing value.  Do not use `||` here.
    scheduledHours: Number.isFinite(staff.scheduled_hours) ? staff.scheduled_hours : null,
    contractedPeriodHours: Number.isFinite(staff.contracted_period_hours) ? staff.contracted_period_hours : null,
  }
}

export function staffInitials(card: Pick<StaffDirectoryCard, 'primaryName'>): string {
  const words = card.primaryName.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '—'
  if (words.length === 1) return Array.from(words[0]).slice(0, 2).join('').toLocaleUpperCase()
  return words.slice(0, 2).map((word) => Array.from(word)[0]).join('').toLocaleUpperCase()
}

export function matchesStaffDirectoryFilter(
  card: StaffDirectoryCard,
  search: string,
  roleCode: string,
): boolean {
  const query = search.trim().toLocaleLowerCase()
  const searchable = [
    card.primaryName,
    card.secondaryName,
    card.roleCode,
    card.unitName,
    card.employmentType,
  ].filter((value): value is string => Boolean(value)).join(' ').toLocaleLowerCase()

  return (roleCode === 'ALL' || card.roleCode === roleCode) && (!query || searchable.includes(query))
}

/** Use a textual source value instead of derived monthly accounting. */
export function sourceHours(value: number | null, unknown: string): string {
  return value === null ? unknown : `${String(value)} h`
}

export function knownStatusLabel(status: string, isZH: boolean): string {
  const labels: Record<string, { zh: string; en: string }> = {
    scheduled: { zh: '已排更', en: 'Scheduled' },
    on_leave: { zh: '休假', en: 'On leave' },
    available: { zh: '可調配', en: 'Available' },
  }
  return labels[status]?.[isZH ? 'zh' : 'en'] ?? status
}
