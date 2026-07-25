"use client"

import { useEffect, useState, useRef } from "react"
import { STAFF, ROSTER } from "@/lib/data"
import { KPIStrip } from "@/components/roster/KPIStrip"
import { StaffCell } from "@/components/roster/StaffCell"
import { ShiftCell } from "@/components/roster/ShiftCell"
import { CreateShiftModal } from "@/components/modals/CreateShiftModal"
import { CreateEventModal } from "@/components/modals/CreateEventModal"
import { useLang } from "@/components/layout/LanguageContext"
import type { ShiftType, DayEntry, Staff } from "@/lib/types"

/* ---------- NAAC types ---------- */
interface NaacShiftDay {
  mealCode?: string
  shiftCode?: string
  taskCode?: string
}

interface NaacShiftRow {
  staffId: number
  position: string
  name: string
  days: NaacShiftDay[]
}

/* ---------- Mapping helpers ---------- */

function mapShiftCode(code: string | undefined): ShiftType {
  if (!code) return "OFF"
  if (code.startsWith("AL")) return "AL"
  if (code.startsWith("SL")) return "AL"
  if (code === "PH" || code === "O" || code === "O,") return "OFF"
  if (code.includes("K10") || code.includes("N10") || code.includes("N1015")) return "N"
  if (code.startsWith("P")) return "P"
  if (code.startsWith("A") || code.startsWith("B") || code.startsWith("G")) return "A"
  return "OFF"
}

function mapTaskCode(taskCode: string | undefined): string[] {
  if (!taskCode) return []
  const tasks: string[] = []
  // Activities & programs
  if (taskCode.includes("電")) tasks.push("715p 語音/視像致電")
  if (taskCode.includes("零")) tasks.push("815p 派零食")
  if (taskCode.includes("Q")) tasks.push("7-8p 高纖茶座")
  if (taskCode.includes("銀")) tasks.push("8-10a 銀色散步")
  if (taskCode.includes("肌")) tasks.push("肌能運動")
  if (taskCode.includes("刷")) tasks.push("830p 協助刷牙")
  if (taskCode.includes("散")) tasks.push("715-830p 外出散步")
  if (taskCode.includes("茗")) tasks.push("7-8p 茗茶班")
  if (taskCode.includes("繪")) tasks.push("7-8p 繪畫班")
  if (taskCode.includes("煮")) tasks.push("7-8p 煮食班")
  if (taskCode.includes("音")) tasks.push("615-7p 房間音樂")
  if (taskCode.includes("站")) tasks.push("外出活動 930a-12p")
  if (taskCode.includes("海")) tasks.push("9-5p 海洋公園")
  if (taskCode.includes("假")) tasks.push("10-2p 飲茶")
  if (taskCode.includes("粉")) tasks.push("粉")
  // Room activities
  if (/d\d+/i.test(taskCode)) {
    const match = taskCode.match(/d(\d+)/i)
    if (match) tasks.push(`房${match[1]}活動`)
  }
  if (/執(\d+)/.test(taskCode)) {
    const match = taskCode.match(/執(\d+)/)
    if (match) tasks.push(`1-230p 執${match[1]}房`)
  }
  // Cleaning & care
  if (taskCode.includes("飯")) tasks.push("9–10p 清潔飯堂")
  if (taskCode.includes("e") && !taskCode.includes("海")) tasks.push("洗衣+搽藥")
  if (taskCode.includes("清")) tasks.push("清潔宿舍範圍")
  if (taskCode.includes("洗") && !taskCode.includes("洗衣")) tasks.push("清洗廁所")
  if (taskCode.includes("餐")) tasks.push("照顧用膳")
  if (taskCode.includes("廚")) tasks.push("130-930p 廚房工作")
  if (taskCode.includes("搬")) tasks.push("搬運工作")
  if (taskCode.includes("天")) tasks.push("10-11a 清天網垃圾")
  if (taskCode.includes("飲")) tasks.push("沖飲品")
  // Medical & visits
  if (taskCode.includes("^")) tasks.push("給藥")
  if (taskCode.includes("*") && !taskCode.includes("*9") && !taskCode.includes("*%")) tasks.push("協助給藥")
  if (taskCode.includes("*9肌") || taskCode.includes("*9")) tasks.push("8-9p 肌能運動+紀錄+營養奶")
  if (/\b(os|pt|st|cp)\b/i.test(taskCode)) tasks.push("到訪服務")
  if (taskCode.includes("陪")) tasks.push("陪診員")
  if (/\bvo\b/i.test(taskCode)) tasks.push("到訪醫生服務")
  if (/\bvp\b/i.test(taskCode)) tasks.push("到訪服務")
  if (taskCode.includes("家")) tasks.push("家人帶診")
  if (taskCode.includes("f") && taskCode.length <= 3) tasks.push("覆診/就診")
  if (taskCode.includes("bp")) tasks.push("pm 量血壓")
  // Records & admin
  if (taskCode.includes("約") || taskCode.includes("©")) tasks.push("約束紀錄")
  if (taskCode.includes("m1") || taskCode.includes("m") && taskCode.length <= 3) tasks.push("會議")
  if (/\bz\d?\b/i.test(taskCode)) tasks.push("培訓活動")
  if (/\bcc\b/i.test(taskCode)) tasks.push("個案會議")
  if (/\bsv\b/i.test(taskCode)) tasks.push("探路")
  if (/\bhv\b/i.test(taskCode)) tasks.push("家訪")
  if (/\bip\b/i.test(taskCode)) tasks.push("個別訓練")
  if (/\bapp\b/i.test(taskCode)) tasks.push("評估")
  if (/\bsup\b/i.test(taskCode)) tasks.push("督導")
  if (/\bin\b/i.test(taskCode) && taskCode.length <= 4) tasks.push("接案")
  if (taskCode.includes("迎")) tasks.push("迎新")
  // Outings
  if (taskCode.includes("@")) tasks.push("外出活動")
  if (taskCode.includes("%")) tasks.push("宿舍內活動")
  if (/\bdn\b|\bdx\b/i.test(taskCode)) tasks.push("聯房活動")
  if (/\btaha\b/i.test(taskCode)) tasks.push("TAHA 一站式服務")
  // Remove duplicates
  return [...new Set(tasks)]
}

/* ---------- Component types ---------- */

type SaveItem = {
  id: string
  type: "create" | "edit" | "delete" | "event"
  title: string
  subtitle: string
  createdAt: string
}

type RangeOption = "thisWeek" | "nextWeek" | "thisMonth" | "custom"

type EditingShift = {
  staffId: number
  dayIndex: number
  shiftType: string
  tasks?: string[]
  mealCode?: string
  note?: string
}

const ZH = {
  title: "每週更表",
  home: "NAAC大興宿舍",
  week: "週",
  month: "月",
  ai_loading: "🤖 生成中...",
  ai_suggest: "🤖 AI更表建議",
  download: "⬇️ 下載更表",
  create_shift: "➕ 新增更次",
  create_event: "📅 新增特別事項",
  save_list: "儲存清單",
  publish_btn: "📤 發佈更改",
  publish_list: "發佈記錄",
  select_range: "選擇時間範圍",
  range_sub: "選擇更表顯示週期",
  this_week: "本週",
  next_week: "下週",
  this_month: "本月",
  custom_range: "自訂範圍",
  start: "開始",
  end: "結束",
  cancel: "取消",
  apply: "套用",
  staff_col: "員工",
  save_title: "儲存清單",
  save_empty: "暫無未發佈的更改",
  publish_title: "發佈記錄",
  publish_empty: "暫無發佈記錄",
  action_edit: "編輯更次",
  action_create: "新增更次",
  action_delete: "刪除更次",
  expected_residents: "預計住客數",
  actual_residents: "實際住客數",
  staff_ratio: "人手比例",
}

const EN = {
  title: "Weekly Roster",
  home: "NAAC Tai Hing Hostel",
  week: "Week",
  month: "Month",
  ai_loading: "🤖 Generating...",
  ai_suggest: "🤖 AI Roster Suggest",
  download: "⬇️ Download Schedule",
  create_shift: "➕ Create Shift",
  create_event: "📅 Create Special Event",
  save_list: "Save List",
  publish_btn: "📤 Publish Change",
  publish_list: "Publish List",
  select_range: "Select time range",
  range_sub: "Choose roster display period",
  this_week: "This week",
  next_week: "Next week",
  this_month: "This month",
  custom_range: "Custom range",
  start: "Start",
  end: "End",
  cancel: "Cancel",
  apply: "Apply",
  staff_col: "Staff Member",
  save_title: "Save List",
  save_empty: "No unpublished changes",
  publish_title: "Publish List",
  publish_empty: "No published records yet",
  action_edit: "Edit Shift",
  action_create: "New Shift",
  action_delete: "Delete Shift",
  expected_residents: "Expected Residents",
  actual_residents: "Actual Residents",
  staff_ratio: "Staff Ratio",
}

const MONTH_SHIFT_CFG: Record<string, { bg: string; color: string }> = {
  A: { bg: "#dbeafe", color: "#1d4ed8" },   // A更 藍色系
  B: { bg: "#e0f2fe", color: "#0369a1" },   // B更 深藍色
  G: { bg: "#dcfce7", color: "#15803d" },   // G更 綠色系
  E: { bg: "#e8f5e9", color: "#2e7d32" },   // E更 深綠
  P: { bg: "#d1fae5", color: "#047857" },   // P更 翡翠綠
  K: { bg: "#1e1b4b", color: "#e0e7ff" },   // K更 深紫黑
  N: { bg: "#1a1a2e", color: "#ffffff" },   // N更 黑色
  "A/N": { bg: "#ede9fe", color: "#6d28d9" }, // A/N更 紫色
  AL: { bg: "#fef3c7", color: "#b45309" },  // 年假 黃色
  SL: { bg: "#fef3c7", color: "#92400e" },  // 病假 深黃
  CL: { bg: "#fde68a", color: "#78350f" },  // 補假 金黃
  PH: { bg: "#fee2e2", color: "#dc2626" },  // 公眾假期 紅色
  OFF: { bg: "#f3f4f6", color: "#6b7280" }, // 休班 灰色
  NO: { bg: "#f5f5f4", color: "#78716c" },  // 通宵後休 淡灰
  SLEEP: { bg: "#ede9fe", color: "#7c3aed" },
  BDL: { bg: "#fef3c7", color: "#d97706" }, // 生日假 橙黃
  FFL: { bg: "#fef3c7", color: "#a16207" }, // 全薪假 棕黃
}

export default function RosterPage() {
  const { lang } = useLang()
  const d = lang === "zh" ? ZH : EN
  const t = (k: keyof typeof ZH) => (d as any)[k]

  // 住客數
  const [expectedResidents, setExpectedResidents] = useState(100)
  const [actualResidents, setActualResidents] = useState(100)

  // 寫入 localStorage 俾 Compliance 用
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("emma-total-residents", String(actualResidents))
    }
  }, [actualResidents])

  const [view, setView] = useState<"week" | "month">("week")
  const [shiftOpen, setShiftOpen] = useState(false)
  const [eventOpen, setEventOpen] = useState(false)
  const [downloadOpen, setDownloadOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [weekOffset, setWeekOffset] = useState(0) // default to week1 (May 25-31)
  const [saveList, setSaveList] = useState<SaveItem[]>([])
  const [publishList, setPublishList] = useState<SaveItem[]>([])
  const [showSaveList, setShowSaveList] = useState(false)
  const [showPublishList, setShowPublishList] = useState(false)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [rangeOption, setRangeOption] = useState<RangeOption>("thisWeek")
  const [customStart, setCustomStart] = useState("2026-06-08")
  const [customEnd, setCustomEnd] = useState("2026-06-14")
  const [editingShift, setEditingShift] = useState<EditingShift | null>(null)
  const calendarRef = useRef<HTMLDivElement | null>(null)

  /* ---------- NAAC Roster state ---------- */
  const [naacRoster, setNaacRoster] = useState<NaacShiftRow[]>([])
  // Month view: stores all 6 weeks keyed by week number
  const [allWeeksData, setAllWeeksData] = useState<Record<string, NaacShiftRow[]>>({})

  // weekOffset 0=week1, 1=week2, ..., 5=week6
  useEffect(() => {
    const weekNum = Math.max(1, Math.min(6, weekOffset + 1))
    fetch(`/api/naac-week?week=${weekNum}`)
      .then(res => res.json())
      .then((data: { rows: NaacShiftRow[]; dates: string[] }) => setNaacRoster(data.rows))
      .catch(() => {})
  }, [weekOffset])

  // Load all 6 weeks for month view
  useEffect(() => {
    if (view !== "month") return
    Promise.all(
      [1,2,3,4,5,6].map(w =>
        fetch(`/api/naac-week?week=${w}`).then(r => r.json()).then(d => ({ week: w, rows: d.rows as NaacShiftRow[] }))
      )
    ).then(results => {
      const map: Record<string, NaacShiftRow[]> = {}
      results.forEach(r => { map[String(r.week)] = r.rows })
      setAllWeeksData(map)
    }).catch(() => {})
  }, [view])

  const handleAI = () => {
    setAiLoading(true)
    setTimeout(() => setAiLoading(false), 1800)
  }

  const formatNow = () =>
    new Date().toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" })

  const addSaveItem = (title: string, subtitle: string, type: SaveItem["type"]) => {
    setSaveList(prev => [
      { id: `${Date.now()}-${Math.random()}`, title, subtitle, type, createdAt: formatNow() },
      ...prev,
    ])
  }

  const handlePublish = () => {
    if (!saveList.length) return
    setPublishList(prev => [...saveList, ...prev])
    setSaveList([])
    setShowSaveList(false)
    setShowPublishList(true)
  }

  // 6-week cycle starts May 25, 2026 (week1). Week3 = Jun 8.
  const baseDate = new Date(2026, 4, 25)
  baseDate.setDate(baseDate.getDate() + weekOffset * 7)
  const endDate = new Date(baseDate)
  endDate.setDate(endDate.getDate() + 6)
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
  const dateLabel = `${months[baseDate.getMonth()]} ${baseDate.getDate()} – ${months[endDate.getMonth()]} ${endDate.getDate()}, ${endDate.getFullYear()}`

  // Generate dynamic DAYS labels for the current week
  const weekDays = ["MON","TUE","WED","THU","FRI","SAT","SUN"]
  const dynamicDays = weekDays.map((wd, i) => {
    const d = new Date(baseDate)
    d.setDate(d.getDate() + i)
    return `${wd} ${d.getDate()}/${d.getMonth() + 1}`
  })

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (!calendarRef.current) return
      if (!calendarRef.current.contains(e.target as Node)) setCalendarOpen(false)
    }
    if (calendarOpen) document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [calendarOpen])

  const applyRange = () => {
    if (rangeOption === "thisWeek")  { setWeekOffset(0); setView("week") }
    if (rangeOption === "nextWeek")  { setWeekOffset(1); setView("week") }
    if (rangeOption === "thisMonth") { setWeekOffset(0); setView("month") }
    if (rangeOption === "custom") {
      const start = new Date(customStart)
      const base  = new Date(2026, 4, 25)
      const diffDays = Math.round((start.getTime() - base.getTime()) / (1000 * 60 * 60 * 24))
      setWeekOffset(Math.round(diffDays / 7))
      setView("week")
    }
    setCalendarOpen(false)
  }

  const RANGE_OPTIONS: { key: RangeOption; label: string }[] = [
    { key: "thisWeek",  label: t("this_week") },
    { key: "nextWeek",  label: t("next_week") },
    { key: "thisMonth", label: t("this_month") },
    { key: "custom",    label: t("custom_range") },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top toolbar */}
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        {/* Row 1 */}
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">{t("title")}</h1>
          <button className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg text-[13px] font-medium hover:bg-gray-50">
            🏠 {t("home")}
            <span className="text-gray-400 text-xs">▾</span>
          </button>

          <div className="ml-auto flex items-center gap-2.5">
            <div className="flex border border-gray-200 rounded-lg overflow-hidden">
              {(["week", "month"] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-3.5 py-1.5 text-xs font-medium transition-all"
                  style={{
                    background: view === v ? "#1a1a2e" : "#fff",
                    color: view === v ? "#fff" : "#6b7280",
                  }}
                >
                  {v === "week" ? t("week") : t("month")}
                </button>
              ))}
            </div>
            <button
              onClick={handleAI}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg transition-colors"
              style={{ background: aiLoading ? "#c8156a" : "#E8187A" }}
            >
              {aiLoading ? t("ai_loading") : t("ai_suggest")}
            </button>
          </div>
        </div>

        {/* Row 2：日期 / 按鈕 */}
        <div className="flex items-center gap-2 relative">
          <button
            onClick={() => setWeekOffset(o => o - 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm"
          >
            ‹
          </button>

          <div className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg bg-white">
            <span className="text-[13px] font-semibold text-gray-900">{dateLabel}</span>
            <button
              type="button"
              onClick={() => setCalendarOpen(v => !v)}
              className="text-gray-400 hover:text-pink-500 transition-colors"
            >
              📅
            </button>
          </div>

          <button
            onClick={() => setWeekOffset(o => o + 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm"
          >
            ›
          </button>

          {/* Range dropdown（保留原邏輯） */}
          {calendarOpen && (
            <div
              ref={calendarRef}
              className="absolute z-20 mt-40 left-10 w-80 rounded-xl border border-gray-200 bg-white shadow-lg p-4"
            >
              <div className="text-xs font-semibold text-gray-800 mb-1">
                {t("select_range")}
              </div>
              <div className="text-[11px] text-gray-500 mb-3">
                {t("range_sub")}
              </div>
              <div className="flex flex-col gap-1 mb-3">
                {RANGE_OPTIONS.map(opt => (
                  <button
                    key={opt.key}
                    onClick={() => setRangeOption(opt.key)}
                    className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs ${
                      rangeOption === opt.key
                        ? "bg-pink-50 text-pink-600"
                        : "hover:bg-gray-50 text-gray-600"
                    }`}
                  >
                    <span>{opt.label}</span>
                    {rangeOption === opt.key && <span>✓</span>}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-2 mb-3">
                <div className="flex-1">
                  <div className="text-[10px] text-gray-500 mb-1">{t("start")}</div>
                  <input
                    type="date"
                    value={customStart}
                    onChange={e => setCustomStart(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1 text-[11px]"
                  />
                </div>
                <div className="flex-1">
                  <div className="text-[10px] text-gray-500 mb-1">{t("end")}</div>
                  <input
                    type="date"
                    value={customEnd}
                    onChange={e => setCustomEnd(e.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1 text-[11px]"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <button
                  className="px-2.5 py-1 text-[11px] rounded-lg border border-gray-200 text-gray-600"
                  onClick={() => setCalendarOpen(false)}
                >
                  {t("cancel")}
                </button>
                <button
                  className="px-2.5 py-1 text-[11px] rounded-lg bg-pink-600 text-white"
                  onClick={applyRange}
                >
                  {t("apply")}
                </button>
              </div>
            </div>
          )}

          <div className="ml-auto flex gap-2">
            <div className="relative">
              <button
                onClick={() => setDownloadOpen(v => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg text-pink-600 border-pink-200 hover:bg-pink-50 transition-colors"
              >
                {t("download")}
              </button>
              {downloadOpen && (
                <div className="absolute top-full mt-1 left-0 z-30 bg-white border border-gray-200 rounded-xl shadow-lg p-2 w-48">
                  {[1,2,3,4,5,6].map(w => (
                    <a
                      key={w}
                      href={`/api/export-naac-week?week=${w}`}
                      className="block px-3 py-2 text-xs text-gray-700 hover:bg-pink-50 rounded-lg transition-colors"
                      onClick={() => setDownloadOpen(false)}
                    >
                      {lang === "zh" ? `第 ${w} 週 (Week ${w})` : `Week ${w}`}
                    </a>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={() => { setEditingShift(null); setShiftOpen(true) }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {t("create_shift")}
            </button>
            <button
              onClick={() => setEventOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              {t("create_event")}
            </button>
            <button
              onClick={() => setShowSaveList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700"
            >
              {t("save_list")} ({saveList.length})
            </button>
            <button
              onClick={handlePublish}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors whitespace-nowrap min-w-[170px] justify-center"
              style={{ background: saveList.length ? "#E8187A" : "#d1d5db" }}
            >
              {t("publish_btn")} ({saveList.length})
            </button>
            <button
              onClick={() => setShowPublishList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700"
            >
              {t("publish_list")} ({publishList.length})
            </button>
          </div>
        </div>

        {/* Row 3：預計 / 實際住客數 + 人手比例 */}
        <div className="mt-2 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold text-gray-600">
              {t("expected_residents")}
            </span>
            <input
              type="number"
              value={expectedResidents}
              onChange={e => setExpectedResidents(Number(e.target.value) || 0)}
              className="w-20 rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-800 bg-gray-50 focus:outline-none focus:border-pink-400"
            />
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-semibold text-gray-600">
              {t("actual_residents")}
            </span>
            <input
              type="number"
              value={actualResidents}
              onChange={e => setActualResidents(Number(e.target.value) || 0)}
              className="w-20 rounded-lg border border-gray-200 px-2 py-1 text-xs text-gray-800 bg-gray-50 focus:outline-none focus:border-pink-400"
            />
          </div>


        </div>
      </div>

            {/* Legend - synced with MONTH_SHIFT_CFG colors */}
      <div className="flex items-center gap-4 px-5 py-2 bg-white border-b border-gray-200 flex-shrink-0 flex-wrap">
        {[
          { color: "#1d4ed8", label: lang === "zh" ? "日更 (A/B/G)" : "Day Shift (A/B/G)" },
          { color: "#047857", label: lang === "zh" ? "P更" : "P Shift" },
          { color: "#1a1a2e", label: lang === "zh" ? "通宵更 (N/K10)" : "Night Shift (N/K10)" },
          { color: "#6d28d9", label: lang === "zh" ? "A/N更" : "A/N Shift" },
          { color: "#b45309", label: lang === "zh" ? "假期 (AL/SL/BDL)" : "Leave (AL/SL/BDL)" },
          { color: "#dc2626", label: lang === "zh" ? "公眾假期 (PH)" : "Public Holiday (PH)" },
          { color: "#6b7280", label: lang === "zh" ? "休息/休班 (O)" : "OFF / Day Off (O)" },
          { color: "#78350f", label: lang === "zh" ? "補假 (CL)" : "Comp. Leave (CL)" },
        ].map(item => (
          <div
            key={item.label}
            className="flex items-center gap-1.5 text-[10px] text-gray-500"
          >
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: item.color }}
            />
            {item.label}
          </div>
        ))}
      </div>

      {/* Main grid */}
      <div className={`grid gap-0 flex-1 min-h-0 ${showSaveList || showPublishList ? "grid-cols-1 xl:grid-cols-[1fr_340px]" : "grid-cols-1"}`}>
        <div className="min-w-0 flex-1 overflow-auto px-5 py-3">
          {view === "week" ? (
            <table
              className="w-full border-collapse bg-white rounded-xl border border-gray-200"
            >
              <thead className="sticky top-0 z-10">
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3.5 py-2.5 text-[10px] font-semibold text-gray-500 border-r border-gray-200 w-52 bg-gray-50">
                    {t("staff_col")}
                  </th>
                  {dynamicDays.map((day, i) => (
                    <th
                      key={day}
                      className="px-2 py-2.5 text-center border-r border-gray-100 last:border-r-0 min-w-24 bg-gray-50"
                    >
                      <div className="text-[9px] text-gray-400 tracking-wide">
                        {day.split(" ")[0]}
                      </div>
                      <div className={`text-[15px] font-bold ${i === 5 || i === 6 ? "text-pink-600" : "text-gray-800"}`}>
                        {day.split(" ")[1]}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {naacRoster.map(row => {
                  // Create a fakeStaff object to feed StaffCell
                  const fakeStaff: Staff = {
                    id: row.staffId,
                    name: row.name,
                    nameEn: row.name || row.position,
                    role: "AW",
                    ward: row.position,
                    floor: "-",
                    certs: [],
                    hoursWorked: 0,
                    hoursTotal: 160,
                    avatar: row.name ? row.name.charAt(row.name.length - 1) : row.position.charAt(0),
                  }

                  return (
                    <tr
                      key={row.staffId}
                      className="border-t border-gray-100 hover:bg-pink-50/30 transition-colors"
                    >
                      <StaffCell staff={fakeStaff} />
                      {row.days.map((day, idx) => {
                        const mappedShiftType = mapShiftCode(day.shiftCode)
                        const mappedTasks = mapTaskCode(day.taskCode)
                        // For OFF/PH days, taskCode often contains the note (e.g. "補1/5", "補25/5")
                        const note = (mappedShiftType === "OFF" || day.shiftCode === "PH") ? day.taskCode : undefined
                        const shift: DayEntry = {
                          type: mappedShiftType,
                          shiftLabel: day.shiftCode || undefined,
                          mealCode: day.mealCode || undefined,
                          note,
                          tasks: mappedTasks,
                        }

                        return (
                          <ShiftCell
                            key={idx}
                            shift={shift}
                            onClick={() => {
                              setEditingShift({
                                staffId: row.staffId,
                                dayIndex: idx,
                                shiftType: day.shiftCode || "",
                                tasks: mappedTasks,
                                mealCode: day.mealCode || undefined,
                                note: note || undefined,
                              })
                              setShiftOpen(true)
                            }}
                          />
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <div className="overflow-x-auto overflow-y-auto" style={{ maxHeight: "calc(100vh - 280px)" }}>
              {(() => {
                // Build 42-day month grid from all 6 weeks
                const totalDays = 42 // 6 weeks × 7 days
                const monthBase = new Date(2026, 4, 25) // Week1 start
                // Generate date headers
                const dateHeaders = Array.from({ length: totalDays }, (_, i) => {
                  const d = new Date(monthBase)
                  d.setDate(d.getDate() + i)
                  return { day: d.getDate(), month: d.getMonth() + 1, weekday: ["日","一","二","三","四","五","六"][d.getDay()] }
                })
                // Get first staff list from any loaded week
                const staffList = allWeeksData["1"] || naacRoster
                return (
                  <table
                    className="border-collapse bg-white rounded-xl border border-gray-200 text-[10px]"
                    style={{ minWidth: "1400px" }}
                  >
                    <thead className="sticky top-0 z-10">
                      <tr className="bg-gray-50 border-b border-gray-200">
                        <th className="text-left px-3 py-1 text-[9px] font-semibold text-gray-500 border-r border-gray-200 w-28 bg-gray-50 sticky left-0 z-20">
                          {t("staff_col")}
                        </th>
                        {dateHeaders.map((dh, i) => (
                          <th
                            key={i}
                            className={`px-0 py-1 text-center border-r border-gray-100 w-9 bg-gray-50 ${dh.weekday === "六" || dh.weekday === "日" ? "bg-pink-50" : ""}`}
                          >
                            <div className="text-[7px] text-gray-400">{dh.weekday}</div>
                            <div className="text-[8px] font-bold text-gray-700">{dh.day}/{dh.month}</div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {staffList.map((row, rowIdx) => {
                        // Build 42-day shift codes from all weeks
                        const allCodes: string[] = []
                        for (let w = 1; w <= 6; w++) {
                          const weekRows = allWeeksData[String(w)]
                          if (weekRows && weekRows[rowIdx]) {
                            weekRows[rowIdx].days.forEach(d => allCodes.push(d.shiftCode || ""))
                          } else {
                            for (let d = 0; d < 7; d++) allCodes.push("")
                          }
                        }
                        return (
                          <tr key={row.staffId || rowIdx} className="border-t border-gray-100 hover:bg-pink-50/20">
                            <td className="px-2 py-1 border-r border-gray-200 bg-gray-50 sticky left-0 z-10">
                              <div className="font-semibold text-gray-900 truncate text-[8px]">
                                {row.name || row.position}
                              </div>
                              <div className="text-gray-400 text-[7px] truncate">
                                {row.position}
                              </div>
                            </td>
                            {allCodes.map((code, i) => {
                              let cfgKey = "OFF"
                              if (code) {
                                if (code.startsWith("AL") || code.startsWith("SL")) cfgKey = "AL"
                                else if (code === "PH" || code === "O" || code === "O,") cfgKey = "OFF"
                                else if (code.includes("N10") || code.includes("N1015") || code.includes("K10")) cfgKey = "A/N"
                                else if (code.startsWith("P")) cfgKey = "P"
                                else if (code.startsWith("A") || code.startsWith("B") || code.startsWith("G")) cfgKey = "A"
                                else cfgKey = "OFF"
                              }
                              const c = MONTH_SHIFT_CFG[cfgKey] ?? MONTH_SHIFT_CFG.OFF
                              return (
                                <td
                                  key={i}
                                  className="px-0 py-0.5 text-center border-r border-gray-50 cursor-pointer"
                                  onClick={() => {
                                    if (code) {
                                      setEditingShift({ staffId: row.staffId, dayIndex: i, shiftType: code, tasks: [] })
                                      setShiftOpen(true)
                                    }
                                  }}
                                >
                                  <span
                                    className="inline-block min-w-[20px] h-3.5 rounded text-[6px] font-bold leading-[14px] text-center px-0.5"
                                    style={{ background: code ? c.bg : "transparent", color: code ? c.color : "transparent" }}
                                  >
                                    {code || ""}
                                  </span>
                                </td>
                              )
                            })}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )
              })()}
            </div>
          )}
        </div>

        {(showSaveList || showPublishList) && (
          <div className="border-l border-gray-200 bg-white overflow-auto xl:min-w-[340px]">
            {showSaveList && (
              <div className="p-4 border-b border-gray-100">
                <h3 className="text-sm font-bold text-gray-900 mb-2">
                  {t("save_title")}
                </h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {saveList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      {t("save_empty")}
                    </div>
                  ) : (
                    saveList.map(item => (
                      <div
                        key={item.id}
                        className="rounded-xl border border-pink-100 bg-pink-50/50 p-3"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-pink-600">
                            {item.title}
                          </span>
                          <span className="text-[10px] text-gray-400">
                            {item.createdAt}
                          </span>
                        </div>
                        <div className="text-[11px] text-gray-600">
                          {item.subtitle}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {showPublishList && (
              <div className="p-4">
                <h3 className="text-sm font-bold text-gray-900 mb-2">
                  {t("publish_title")}
                </h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {publishList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      {t("publish_empty")}
                    </div>
                  ) : (
                    publishList.map(item => (
                      <div
                        key={item.id}
                        className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-emerald-700">
                            {item.title}
                          </span>
                          <span className="text-[10px] text-gray-400">
                            {item.createdAt}
                          </span>
                        </div>
                        <div className="text-[11px] text-gray-600">
                          {item.subtitle}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <CreateShiftModal
        open={shiftOpen}
        onClose={() => { setShiftOpen(false); setEditingShift(null) }}
        mode={editingShift ? "edit" : "create"}
        initialShift={editingShift}
        onSaveChange={(payload: { shiftType: string }) => {
          const staffName = editingShift
            ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn
              || naacRoster.find(r => r.staffId === editingShift.staffId)?.name
              || "Staff"
            : "New Shift"
          addSaveItem(
            editingShift ? t("action_edit") : t("action_create"),
            `${staffName} · ${payload.shiftType}`,
            editingShift ? "edit" : "create",
          )
          setShiftOpen(false)
          setEditingShift(null)
        }}
        onDeleteShift={() => {
          const staffName = editingShift
            ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn
              || naacRoster.find(r => r.staffId === editingShift.staffId)?.name
              || "Staff"
            : "Staff"
          addSaveItem(
            t("action_delete"),
            `${staffName} · ${editingShift?.shiftType || "shift"}`,
            "delete",
          )
          setShiftOpen(false)
          setEditingShift(null)
        }}
      />

      <CreateEventModal open={eventOpen} onClose={() => setEventOpen(false)} />
    </div>
  )
}
