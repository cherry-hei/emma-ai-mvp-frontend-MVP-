// Domain vocabulary in both languages: rank codes, shift codes, leave codes,
// statuses. One place, because these strings appear on ten screens.
//
// WHY THIS FILE EXISTS
//
// Rank codes were rendered as bare Latin abbreviations in Chinese mode - the ROI
// table printed "HCA" and "HW" whatever language was selected. A zh reader then
// gets an English page with a few Chinese labels, and the browser offers to
// translate it. Accepting that offer is what produced the reported "氫氯噻嗪"
// (hydrochlorothiazide - a diuretic) for HCA and "硬體" (computer hardware) for
// HW. Neither string was ever in our code.
//
// So the rule: never ship a bare code to a zh reader. Translate it here, and the
// browser has nothing left to mistranslate.
//
// TERMINOLOGY SOURCE: the homes' own duty rosters, via the RBAC definition doc
// (30 Jul 2026) - 保健員 HW, 院舍護理員 RCW, 個人照顧員 PCW, 社工 SW,
// 物理治療師 PT, 職業治療師 OT are the NGOs' own words, not a dictionary's.
// Hong Kong usage, Traditional characters.

export type Lang = 'en' | 'zh'

interface Term {
  en: string
  zh: string
  /** Shown after the zh label so the code stays recognisable on a bilingual floor. */
  keepCode?: boolean
}

// ── staff ranks ─────────────────────────────────────────────────────────────
export const RANKS: Record<string, Term> = {
  RN:   { en: 'Registered Nurse',            zh: '註冊護士',     keepCode: true },
  EN:   { en: 'Enrolled Nurse',              zh: '登記護士',     keepCode: true },
  HW:   { en: 'Health Worker',               zh: '保健員',       keepCode: true },
  HCA:  { en: 'Health Care Assistant',       zh: '健康護理員',   keepCode: true },
  RCW:  { en: 'Residential Care Worker',     zh: '院舍護理員',   keepCode: true },
  CW:   { en: 'Care Worker',                 zh: '護理員',       keepCode: true },
  PCW:  { en: 'Personal Care Worker',        zh: '個人照顧員',   keepCode: true },
  AW:   { en: 'Assistant Worker',            zh: '助理員',       keepCode: true },
  WA:   { en: 'Ward Assistant',              zh: '助理員',       keepCode: true },
  PTA:  { en: 'Physiotherapy Assistant',     zh: '物理治療助理', keepCode: true },
  OTA:  { en: 'Occupational Therapy Asst.',  zh: '職業治療助理', keepCode: true },
  SW:   { en: 'Social Worker',               zh: '社工',         keepCode: true },
  PT:   { en: 'Physiotherapist',             zh: '物理治療師',   keepCode: true },
  OT:   { en: 'Occupational Therapist',      zh: '職業治療師',   keepCode: true },
  WM:   { en: 'Workman',                     zh: '工友',         keepCode: true },
}

// ── shift / duty codes ──────────────────────────────────────────────────────
// Single letters are left alone: they are the same mark on the paper roster in
// both languages, and a home reads "A更" not "早更" off the grid.
export const SHIFTS: Record<string, Term> = {
  A:     { en: 'Morning',        zh: '早更' },
  B:     { en: 'Day',            zh: '日更' },
  E:     { en: 'Evening',        zh: '黃昏更' },
  P:     { en: 'Afternoon',      zh: '午更' },
  N:     { en: 'Night',          zh: '夜更' },
  AN:    { en: 'Overnight',      zh: '通宵更' },
  D:     { en: 'Day (AS)',       zh: '日更（助理院長）' },
  OFF:   { en: 'Off',            zh: '休息' },
  DO:    { en: 'Day Off',        zh: '例假' },
  SLEEP: { en: 'Sleep-in',       zh: '留宿' },
}

// ── leave / absence codes ───────────────────────────────────────────────────
export const LEAVE: Record<string, Term> = {
  AL:   { en: 'Annual Leave',        zh: '年假' },
  SL:   { en: 'Sick Leave',          zh: '病假' },
  DSL:  { en: 'Doctor Sick Leave',   zh: '疾病津貼假' },
  CL:   { en: 'Casual Leave',        zh: '事假' },
  VL:   { en: 'Vacation Leave',      zh: '大假' },
  FAL:  { en: 'Family Leave',        zh: '家庭假' },
  ML:   { en: 'Maternity Leave',     zh: '產假' },
  PL:   { en: 'Paternity Leave',     zh: '侍產假' },
  NPL:  { en: 'No-Pay Leave',        zh: '無薪假' },
  BDL:  { en: 'Birthday Leave',      zh: '生日假' },
  FUNL: { en: 'Funeral Leave',       zh: '恩恤假' },
  TOIL: { en: 'Time Off In Lieu',    zh: '補假' },
}

// ── request / approval statuses ─────────────────────────────────────────────
export const STATUSES: Record<string, Term> = {
  pending:     { en: 'Pending',     zh: '待審批' },
  recommended: { en: 'Recommended', zh: '已建議' },
  approved:    { en: 'Approved',    zh: '已批准' },
  rejected:    { en: 'Rejected',    zh: '已拒絕' },
  cancelled:   { en: 'Cancelled',   zh: '已取消' },
  revoked:     { en: 'Revoked',     zh: '已撤回' },
  draft:       { en: 'Draft',       zh: '草稿' },
  published:   { en: 'Published',   zh: '已發佈' },
  archived:    { en: 'Archived',    zh: '已封存' },
}

function look(table: Record<string, Term>, code: string | null | undefined, lang: Lang): string {
  if (!code) return ''
  const term = table[code] ?? table[code.toUpperCase()]
  // An unknown code is returned verbatim rather than blanked - a roster cell
  // showing a code we have not catalogued is far better than an empty one.
  if (!term) return code
  if (lang !== 'zh') return term.en
  return term.keepCode ? `${term.zh}（${code}）` : term.zh
}

/** "HCA" -> "健康護理員（HCA）" in zh, "Health Care Assistant" in en. */
export const rankLabel = (code: string | null | undefined, lang: Lang) => look(RANKS, code, lang)

/** Short form for dense grids and table headers: "健康護理員" / "HCA". */
export function rankShort(code: string | null | undefined, lang: Lang): string {
  if (!code) return ''
  return lang === 'zh' ? (RANKS[code]?.zh ?? RANKS[code.toUpperCase()]?.zh ?? code) : code
}

export const shiftLabel = (code: string | null | undefined, lang: Lang) => look(SHIFTS, code, lang)
export const leaveLabel = (code: string | null | undefined, lang: Lang) => look(LEAVE, code, lang)
export const statusLabel = (code: string | null | undefined, lang: Lang) =>
  look(STATUSES, code?.toLowerCase(), lang)
