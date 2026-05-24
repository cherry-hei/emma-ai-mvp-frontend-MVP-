"use client"

import { useEffect, useState, useRef } from "react"
import { STAFF, ROSTER, DAYS } from "@/lib/data"
import { KPIStrip } from "@/components/roster/KPIStrip"
import { StaffCell } from "@/components/roster/StaffCell"
import { ShiftCell } from "@/components/roster/ShiftCell"
import { CreateShiftModal } from "@/components/modals/CreateShiftModal"
import { CreateEventModal } from "@/components/modals/CreateEventModal"
import { useLang } from "@/components/layout/LanguageContext"

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
}

const ZH = {
  title:         "每週更表",
  home:          "康寧安老院",
  week:          "週",
  month:         "月",
  ai_loading:    "🤖 生成中...",
  ai_suggest:    "🤖 AI更表建議",
  download:      "⬇️ 下載更表",
  create_shift:  "➕ 新增更次",
  create_event:  "📅 新增特別事項",
  save_list:     "儲存清單",
  publish_btn:   "📤 發佈更改",
  publish_list:  "發佈記錄",
  select_range:  "選擇時間範圍",
  range_sub:     "選擇更表顯示週期",
  this_week:     "本週",
  next_week:     "下週",
  this_month:    "本月",
  custom_range:  "自訂範圍",
  start:         "開始",
  end:           "結束",
  cancel:        "取消",
  apply:         "套用",
  staff_col:     "員工",
  save_title:    "儲存清單",
  save_empty:    "暫無未發佈的更改",
  publish_title: "發佈記錄",
  publish_empty: "暫無發佈記錄",
  action_edit:   "編輯更次",
  action_create: "新增更次",
  action_delete: "刪除更次",
  legend_a:      "A更 (07:00–15:00)",
  legend_b:      "B更 (08:00–16:00)",
  legend_e:      "E更 (09:00–17:00)",
  legend_p:      "P更 (13:30–21:30)",
  legend_an:     "A/N更 (07:00–13:30 / 21:30–07:00)",
  legend_al:     "AL (年假)",
  legend_off:    "休息",
  legend_sleep:  "睡眠日",
}

const EN = {
  title:         "Weekly Roster",
  home:          "Haven Elderly Home",
  week:          "Week",
  month:         "Month",
  ai_loading:    "🤖 Generating...",
  ai_suggest:    "🤖 AI Roster Suggest",
  download:      "⬇️ Download Schedule",
  create_shift:  "➕ Create Shift",
  create_event:  "📅 Create Special Event",
  save_list:     "Save List",
  publish_btn:   "📤 Publish Change",
  publish_list:  "Publish List",
  select_range:  "Select time range",
  range_sub:     "Choose roster display period",
  this_week:     "This week",
  next_week:     "Next week",
  this_month:    "This month",
  custom_range:  "Custom range",
  start:         "Start",
  end:           "End",
  cancel:        "Cancel",
  apply:         "Apply",
  staff_col:     "Staff Member",
  save_title:    "Save List",
  save_empty:    "No unpublished changes",
  publish_title: "Publish List",
  publish_empty: "No published records yet",
  action_edit:   "Edit Shift",
  action_create: "New Shift",
  action_delete: "Delete Shift",
  legend_a:      "A SHIFT (07:00–15:00)",
  legend_b:      "B SHIFT (08:00–16:00)",
  legend_e:      "E SHIFT (09:00–17:00)",
  legend_p:      "P SHIFT (13:30–21:30)",
  legend_an:     "A/N SHIFT (07:00–13:30 / 21:30–07:00)",
  legend_al:     "AL (Annual Leave)",
  legend_off:    "DAY OFF",
  legend_sleep:  "SLEEPING DAY",
}

export default function RosterPage() {
  const { lang } = useLang()
  const d = lang === "zh" ? ZH : EN
  const t = (k: keyof typeof ZH) => d[k]

  const [view, setView] = useState<"week" | "month">("week")
  const [shiftOpen, setShiftOpen] = useState(false)
  const [eventOpen, setEventOpen] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [weekOffset, setWeekOffset] = useState(0)
  const [saveList, setSaveList] = useState<SaveItem[]>([])
  const [publishList, setPublishList] = useState<SaveItem[]>([])
  const [showSaveList, setShowSaveList] = useState(false)
  const [showPublishList, setShowPublishList] = useState(false)
  const [calendarOpen, setCalendarOpen] = useState(false)
  const [rangeOption, setRangeOption] = useState<RangeOption>("thisWeek")
  const [customStart, setCustomStart] = useState("2026-03-23")
  const [customEnd, setCustomEnd] = useState("2026-03-29")
  const [editingShift, setEditingShift] = useState<EditingShift | null>(null)
  const calendarRef = useRef<HTMLDivElement | null>(null)

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

  const baseDate = new Date(2026, 2, 23)
  baseDate.setDate(baseDate.getDate() + weekOffset * 7)
  const endDate = new Date(baseDate)
  endDate.setDate(endDate.getDate() + 6)
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
  const dateLabel = `${months[baseDate.getMonth()]} ${baseDate.getDate()} – ${months[endDate.getMonth()]} ${endDate.getDate()}, ${endDate.getFullYear()}`

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
      const base  = new Date(2026, 2, 23)
      const diffDays = Math.round((start.getTime() - base.getTime()) / (1000 * 60 * 60 * 24))
      setWeekOffset(Math.round(diffDays / 7))
      setView("week")
    }
    setCalendarOpen(false)
  }

  const LEGENDS = [
    { color: "#3b82f6", label: t("legend_a") },
    { color: "#93c5fd", label: t("legend_b") },
    { color: "#86efac", label: t("legend_e") },
    { color: "#10b981", label: t("legend_p") },
    { color: "#8b5cf6", label: t("legend_an") },
    { color: "#fbbf24", label: t("legend_al") },
    { color: "#9ca3af", label: t("legend_off") },
    { color: "#a78bfa", label: t("legend_sleep") },
  ]

  const RANGE_OPTIONS: { key: RangeOption; label: string }[] = [
    { key: "thisWeek",  label: t("this_week") },
    { key: "nextWeek",  label: t("next_week") },
    { key: "thisMonth", label: t("this_month") },
    { key: "custom",    label: t("custom_range") },
  ]

  const MONTH_SHIFT_CFG: Record<string, { bg: string; color: string }> = {
    A:     { bg: "#dbeafe", color: "#1d4ed8" },
    B:     { bg: "#e0f2fe", color: "#2563eb" },
    E:     { bg: "#dcfce7", color: "#15803d" },
    P:     { bg: "#d1fae5", color: "#047857" },
    "A/N": { bg: "#ede9fe", color: "#6d28d9" },
    AL:    { bg: "#fef3c7", color: "#b45309" },
    OFF:   { bg: "#f3f4f6", color: "#6b7280" },
    SLEEP: { bg: "#ede9fe", color: "#7c3aed" },
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Top toolbar ── */}
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
                <button key={v} onClick={() => setView(v)}
                  className="px-3.5 py-1.5 text-xs font-medium transition-all"
                  style={{ background: view === v ? "#1a1a2e" : "#fff", color: view === v ? "#fff" : "#6b7280" }}>
                  {v === "week" ? t("week") : t("month")}
                </button>
              ))}
            </div>
            <button onClick={handleAI}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg transition-colors"
              style={{ background: aiLoading ? "#c8156a" : "#E8187A" }}>
              {aiLoading ? t("ai_loading") : t("ai_suggest")}
            </button>
          </div>
        </div>

        {/* Row 2 */}
        <div className="flex items-center gap-2 relative">
          <button onClick={() => setWeekOffset(o => o - 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm">
            ‹
          </button>

          <div className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg bg-white">
            <span className="text-[13px] font-semibold text-gray-900">{dateLabel}</span>
            <button type="button" onClick={() => setCalendarOpen(v => !v)}
              className="text-gray-400 hover:text-pink-500 transition-colors">
              📅
            </button>
          </div>

          <button onClick={() => setWeekOffset(o => o + 1)}
            className="w-7 h-7 rounded-md border border-gray-200 flex items-center justify-center text-gray-500 hover:bg-gray-50 text-sm">
            ›
          </button>

          {calendarOpen && (
            <div ref={calendarRef}
              className="absolute left-10 top-12 z-30 w-[340px] rounded-2xl border border-gray-200 bg-white p-4 shadow-2xl">
              <h3 className="text-sm font-bold text-gray-900">{t("select_range")}</h3>
              <p className="mt-1 text-xs text-gray-500">{t("range_sub")}</p>
              <div className="mt-4 space-y-2">
                {RANGE_OPTIONS.map(item => (
                  <button key={item.key} type="button"
                    onClick={() => setRangeOption(item.key)}
                    className="flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm"
                    style={{
                      background:   rangeOption === item.key ? "#fdf2f8" : "#fff",
                      borderColor:  rangeOption === item.key ? "#f9a8d4" : "#e5e7eb",
                      color:        rangeOption === item.key ? "#be185d" : "#374151",
                    }}>
                    <span>{item.label}</span>
                    <span>{rangeOption === item.key ? "✓" : ""}</span>
                  </button>
                ))}
              </div>
              {rangeOption === "custom" && (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-gray-500">{t("start")}</label>
                    <input type="date" value={customStart} onChange={e => setCustomStart(e.target.value)}
                      className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm" />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-gray-500">{t("end")}</label>
                    <input type="date" value={customEnd} onChange={e => setCustomEnd(e.target.value)}
                      className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm" />
                  </div>
                </div>
              )}
              <div className="mt-4 flex items-center justify-between">
                <button type="button" onClick={() => setCalendarOpen(false)}
                  className="text-xs font-semibold text-gray-500">{t("cancel")}</button>
                <button type="button" onClick={applyRange}
                  className="rounded-xl px-4 py-2 text-xs font-semibold text-white"
                  style={{ background: "#E8187A" }}>{t("apply")}</button>
              </div>
            </div>
          )}

          <div className="ml-auto flex gap-2">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border rounded-lg text-pink-600 border-pink-200 hover:bg-pink-50 transition-colors">
              {t("download")}
            </button>
            <button onClick={() => { setEditingShift(null); setShiftOpen(true) }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
              {t("create_shift")}
            </button>
            <button onClick={() => setEventOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
              {t("create_event")}
            </button>
            <button onClick={() => setShowSaveList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700">
              {t("save_list")} ({saveList.length})
            </button>
            <button onClick={handlePublish}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors whitespace-nowrap min-w-[170px] justify-center"
              style={{ background: saveList.length ? "#E8187A" : "#d1d5db" }}>
              {t("publish_btn")} ({saveList.length})
            </button>
            <button onClick={() => setShowPublishList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700">
              {t("publish_list")} ({publishList.length})
            </button>
          </div>
        </div>
      </div>

      {/* ── Legend ── */}
      <div className="flex items-center gap-5 px-5 py-2 bg-white border-b border-gray-200 flex-shrink-0 overflow-x-auto whitespace-nowrap">
        {LEGENDS.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5 text-[10px] text-gray-500 shrink-0">
            <div className="w-2 h-2 rounded-full" style={{ background: color }} />
            {label}
          </div>
        ))}
      </div>

      <KPIStrip />

      {/* ── Main grid ── */}
      <div className={`grid gap-0 flex-1 min-h-0 ${showSaveList || showPublishList ? "grid-cols-1 xl:grid-cols-[1fr_340px]" : "grid-cols-1"}`}>
        <div className="min-w-0 flex-1 overflow-auto px-5 py-3">

          {/* Week view */}
          {view === "week" ? (
            <table className="w-full border-collapse bg-white rounded-xl border border-gray-200"
              style={{ borderRadius: "12px", overflow: "hidden" }}>
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3.5 py-2.5 text-[10px] font-semibold text-gray-500 border-r border-gray-200 w-52">
                    {t("staff_col")}
                  </th>
                  {DAYS.map((day, i) => (
                    <th key={day} className="px-2 py-2.5 text-center border-r border-gray-100 last:border-r-0 min-w-24">
                      <div className="text-[9px] text-gray-400 tracking-wide">{day.split(" ")[0]}</div>
                      <div className={`text-[15px] font-bold ${i === 3 ? "text-pink-600" : "text-gray-800"}`}>{day.split(" ")[1]}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROSTER.map(row => {
                  const staff = STAFF.find(s => s.id === row.staffId)!
                  return (
                    <tr key={row.staffId} className="border-t border-gray-100 hover:bg-pink-50/30 transition-colors">
                      <StaffCell staff={staff} />
                      {row.days.map((shift, idx) => (
                        <ShiftCell
                          key={idx}
                          shift={shift}
                          onClick={() => {
                            setEditingShift({
                              staffId: row.staffId,
                              dayIndex: idx,
                              shiftType: shift.type,
                              tasks: shift.tasks || [],
                            })
                            setShiftOpen(true)
                          }}
                        />
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>

          ) : (
            /* Month view */
            <div className="overflow-x-auto">
              <table className="border-collapse bg-white rounded-xl border border-gray-200 text-[10px]" style={{ minWidth: "1100px" }}>
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-3 py-2 text-[9px] font-semibold text-gray-500 border-r border-gray-200 w-36">
                      {t("staff_col")}
                    </th>
                    {Array.from({ length: 31 }, (_, i) => (
                      <th key={i} className="px-0.5 py-2 text-[9px] text-gray-400 text-center border-r border-gray-100 w-8">{i + 1}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {STAFF.map(s => {
                    const shiftTypes = ["A","B","E","P","A/N","AL","OFF","SLEEP","A","B","P","OFF","A/N","AL","E","P","OFF","SLEEP","A","P","B","E","AL","OFF","A/N","P","E","B","SLEEP","OFF","AL"]
                    return (
                      <tr key={s.id} className="border-t border-gray-100 hover:bg-pink-50/20">
                        <td className="px-2.5 py-1.5 border-r border-gray-200 bg-gray-50">
                          <div className="font-semibold text-gray-900 truncate">{s.nameEn.split(" ").slice(-1)[0]}</div>
                          <div className="text-gray-400 text-[8px]">{s.role} · {s.floor}</div>
                        </td>
                        {shiftTypes.map((st, i) => {
                          const c = MONTH_SHIFT_CFG[st] ?? MONTH_SHIFT_CFG.OFF
                          return (
                            <td key={i}
                              className="px-0.5 py-1 text-center border-r border-gray-50 cursor-pointer"
                              onClick={() => {
                                setEditingShift({ staffId: s.id, dayIndex: i, shiftType: st, tasks: [] })
                                setShiftOpen(true)
                              }}>
                              <span className="inline-block min-w-[22px] h-4 rounded text-[8px] font-bold leading-4 text-center px-1"
                                style={{ background: c.bg, color: c.color }}>{st}</span>
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Side panel */}
        {(showSaveList || showPublishList) && (
          <div className="border-l border-gray-200 bg-white overflow-auto xl:min-w-[340px]">
            {showSaveList && (
              <div className="p-4 border-b border-gray-100">
                <h3 className="text-sm font-bold text-gray-900 mb-2">{t("save_title")}</h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {saveList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      {t("save_empty")}
                    </div>
                  ) : saveList.map(item => (
                    <div key={item.id} className="rounded-xl border border-pink-100 bg-pink-50/50 p-3">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-semibold text-pink-600">{item.title}</span>
                        <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                      </div>
                      <div className="text-[11px] text-gray-600">{item.subtitle}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {showPublishList && (
              <div className="p-4">
                <h3 className="text-sm font-bold text-gray-900 mb-2">{t("publish_title")}</h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {publishList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      {t("publish_empty")}
                    </div>
                  ) : publishList.map(item => (
                    <div key={item.id} className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-semibold text-emerald-700">{item.title}</span>
                        <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                      </div>
                      <div className="text-[11px] text-gray-600">{item.subtitle}</div>
                    </div>
                  ))}
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
            ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn || "Staff"
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
            ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn || "Staff"
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