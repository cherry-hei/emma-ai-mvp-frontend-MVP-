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
  HCA:  { en: 'Health Care Assistant',       zh: '健康服務助理', keepCode: true },
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
  // UNRESOLVED - Cherry's 1 Aug review says WM = 院舍經理 (residential care home
  // manager). Left as 工友 because her own NAAC files say the opposite, and
  // loudly: NAAC編更安排1.docx section 6 is headed "WM (Workman) Staffing" and
  // rosters two WM Monday to Saturday and one on Sunday, on A8x and A9x shifts.
  // Nobody rosters two home managers onto an 08:00 and an 09:00 shift six days a
  // week.
  //
  // Applying the change would relabel every workman in the imported roster as the
  // person who runs the building - visible on the roster grid, in the staff
  // portfolio and in the SWD reports. Getting it wrong in that direction is worse
  // than leaving it, so it stays until she confirms which code she meant. There
  // is no manager rank in `Rank` at all, which is the likelier gap.
  WM:   { en: 'Workman',                     zh: '工友',         keepCode: true },
}

// ── shift / duty codes ──────────────────────────────────────────────────────
// The letter is the label, in both languages: "A更" / "A shift", never "早更" /
// "Morning". Confirmed by Cherry, 1 Aug 2026.
//
// Time-of-day names are not just unidiomatic here, they are wrong. Both NGOs use
// the same A/P/N letters but hang different hours off them - NAAC's A shift is
// 07:15-15:15, and its A230 runs 14:30-22:30, which no reader would call
// "morning". The letter is what is printed on the paper roster and what staff
// say out loud; the hours come from the facility's own shift dictionary
// (`shift_definitions`), not from the name.
export const SHIFTS: Record<string, Term> = {
  A:     { en: 'A shift',        zh: 'A更' },
  B:     { en: 'B shift',        zh: 'B更' },
  E:     { en: 'E shift',        zh: 'E更' },
  P:     { en: 'P shift',        zh: 'P更' },
  N:     { en: 'N shift',        zh: 'N更' },
  AN:    { en: 'AN shift',       zh: 'AN更' },
  D:     { en: 'D shift (AS)',   zh: 'D更（助理院長）' },
  NO:    { en: 'Post-night rest', zh: '通宵更後休息' },
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
