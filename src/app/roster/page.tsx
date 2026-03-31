"use client"

import { useEffect, useState, useRef } from "react"
import { STAFF, ROSTER, DAYS } from "@/lib/data"
import { KPIStrip } from "@/components/roster/KPIStrip"
import { StaffCell } from "@/components/roster/StaffCell"
import { ShiftCell } from "@/components/roster/ShiftCell"
import { CreateShiftModal } from "@/components/modals/CreateShiftModal"
import { CreateEventModal } from "@/components/modals/CreateEventModal"

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

export default function RosterPage() {
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
    new Date().toLocaleTimeString("en-HK", {
      hour: "2-digit",
      minute: "2-digit",
    })

  const addSaveItem = (title: string, subtitle: string, type: SaveItem["type"]) => {
    setSaveList(prev => [
      {
        id: `${Date.now()}-${Math.random()}`,
        title,
        subtitle,
        type,
        createdAt: formatNow(),
      },
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
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  const dateLabel = `${months[baseDate.getMonth()]} ${baseDate.getDate()} — ${months[endDate.getMonth()]} ${endDate.getDate()}, ${endDate.getFullYear()}`

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (!calendarRef.current) return
      if (!calendarRef.current.contains(e.target as Node)) {
        setCalendarOpen(false)
      }
    }

    if (calendarOpen) {
      document.addEventListener("mousedown", handleClickOutside)
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
    }
  }, [calendarOpen])

  const applyRange = () => {
    if (rangeOption === "thisWeek") {
      setWeekOffset(0)
      setView("week")
    }

    if (rangeOption === "nextWeek") {
      setWeekOffset(1)
      setView("week")
    }

    if (rangeOption === "thisMonth") {
      setWeekOffset(0)
      setView("month")
    }

    if (rangeOption === "custom") {
      const start = new Date(customStart)
      const base = new Date(2026, 2, 23)
      const diffDays = Math.round((start.getTime() - base.getTime()) / (1000 * 60 * 60 * 24))
      setWeekOffset(Math.round(diffDays / 7))
      setView("week")
    }

    setCalendarOpen(false)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="bg-white border-b border-gray-200 px-5 py-3 flex-shrink-0 space-y-2.5">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-gray-900">Weekly Roster 更表</h1>
          <button className="flex items-center gap-2 px-3 py-1.5 border border-gray-200 rounded-lg text-[13px] font-medium hover:bg-gray-50">
            🏠 Haven Elderly Home
            <span className="text-gray-400 text-xs">▾</span>
          </button>

          <div className="ml-auto flex items-center gap-2.5">
            <div className="flex border border-gray-200 rounded-lg overflow-hidden">
              {(["week", "month"] as const).map(v => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className="px-3.5 py-1.5 text-xs font-medium transition-all capitalize"
                  style={{
                    background: view === v ? "#1a1a2e" : "#fff",
                    color: view === v ? "#fff" : "#6b7280",
                  }}
                >
                  {v === "week" ? "Week" : "Month"}
                </button>
              ))}
            </div>

            <button
              onClick={handleAI}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-white text-xs font-semibold rounded-lg transition-colors"
              style={{ background: aiLoading ? "#c8156a" : "#E8187A" }}
            >
              {aiLoading ? "✦ 計算中..." : "✦ AI排更建議"}
            </button>
          </div>
        </div>

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

          {calendarOpen && (
            <div
              ref={calendarRef}
              className="absolute left-10 top-12 z-30 w-[340px] rounded-2xl border border-gray-200 bg-white p-4 shadow-2xl"
            >
              <h3 className="text-sm font-bold text-gray-900">Select time range</h3>
              <p className="mt-1 text-xs text-gray-500">選擇 Weekly Roster 顯示時間段</p>

              <div className="mt-4 space-y-2">
                {[
                  { key: "thisWeek", label: "This week" },
                  { key: "nextWeek", label: "Next week" },
                  { key: "thisMonth", label: "This month" },
                  { key: "custom", label: "Custom range" },
                ].map(item => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setRangeOption(item.key as RangeOption)}
                    className="flex w-full items-center justify-between rounded-xl border px-3 py-2 text-sm"
                    style={{
                      background: rangeOption === item.key ? "#fdf2f8" : "#fff",
                      borderColor: rangeOption === item.key ? "#f9a8d4" : "#e5e7eb",
                      color: rangeOption === item.key ? "#be185d" : "#374151",
                    }}
                  >
                    <span>{item.label}</span>
                    <span>{rangeOption === item.key ? "✓" : ""}</span>
                  </button>
                ))}
              </div>

              {rangeOption === "custom" && (
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-gray-500">Start</label>
                    <input
                      type="date"
                      value={customStart}
                      onChange={e => setCustomStart(e.target.value)}
                      className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-gray-500">End</label>
                    <input
                      type="date"
                      value={customEnd}
                      onChange={e => setCustomEnd(e.target.value)}
                      className="w-full rounded-xl border border-gray-200 bg-gray-50 px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}

              <div className="mt-4 flex items-center justify-between">
                <button type="button" onClick={() => setCalendarOpen(false)} className="text-xs font-semibold text-gray-500">
                  Cancel
                </button>
                <button type="button" onClick={applyRange} className="rounded-xl px-4 py-2 text-xs font-semibold text-white" style={{ background: "#E8187A" }}>
                  Apply
                </button>
              </div>
            </div>
          )}

          <div className="ml-auto flex gap-2">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 text-pink-600 border-pink-200 hover:bg-pink-50 transition-colors">
              ⬇ Download Schedule
            </button>

            <button
              onClick={() => {
                setEditingShift(null)
                setShiftOpen(true)
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ＋ Create Shift
            </button>

            <button
              onClick={() => setEventOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              ✦ Create Special Event
            </button>

            <button
              onClick={() => setShowSaveList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700"
            >
              Save List ({saveList.length})
            </button>

            <button
              onClick={handlePublish}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors whitespace-nowrap min-w-[170px] justify-center"
              style={{ background: saveList.length ? "#E8187A" : "#d1d5db" }}
            >
              ✓ Publish Change ({saveList.length})
            </button>

            <button
              onClick={() => setShowPublishList(v => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 bg-white text-gray-700"
            >
              Publish List ({publishList.length})
            </button>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-5 px-5 py-2 bg-white border-b border-gray-200 flex-shrink-0 overflow-x-auto whitespace-nowrap">
        {[
          { color: "#3b82f6", label: "A SHIFT (07:00–15:00)" },
          { color: "#93c5fd", label: "B SHIFT (08:00–16:00)" },
          { color: "#86efac", label: "E SHIFT (09:00–17:00)" },
          { color: "#10b981", label: "P SHIFT (13:30–21:30)" },
          { color: "#8b5cf6", label: "A/N SHIFT (07:00–13:30 / 21:30–07:00)" },
          { color: "#fbbf24", label: "AL (年假)" },
          { color: "#9ca3af", label: "DAY OFF" },
          { color: "#a78bfa", label: "SLEEPING DAY" },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-1.5 text-[10px] text-gray-500 shrink-0">
            <div className="w-2 h-2 rounded-full" style={{ background: color }} />
            {label}
          </div>
        ))}
      </div>

      <KPIStrip />

      <div className={`grid gap-0 flex-1 min-h-0 ${showSaveList || showPublishList ? "grid-cols-1 xl:grid-cols-[1fr_340px]" : "grid-cols-1"}`}>
        <div className="min-w-0 flex-1 overflow-auto px-5 py-3">
          {view === "week" ? (
            <table
              className="w-full border-collapse bg-white rounded-xl border border-gray-200 overflow-hidden"
              style={{ borderRadius: "12px", overflow: "hidden" }}
            >
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-3.5 py-2.5 text-[10px] font-semibold text-gray-500 border-r border-gray-200 w-52">
                    STAFF MEMBER
                  </th>
                  {DAYS.map((d, i) => (
                    <th key={d} className="px-2 py-2.5 text-center border-r border-gray-100 last:border-r-0 min-w-24">
                      <div className="text-[9px] text-gray-400 tracking-wide">{d.split(" ")[0]}</div>
                      <div className={`text-[15px] font-bold ${i === 3 ? "text-pink-600" : "text-gray-800"}`}>
                        {d.split(" ")[1]}
                      </div>
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
                        <td
                          key={idx}
                          onClick={() => {
                            setEditingShift({
                              staffId: row.staffId,
                              dayIndex: idx,
                              shiftType: shift.type,
                              tasks: shift.tasks || [],
                            })
                            setShiftOpen(true)
                          }}
                          className="border-r border-gray-100 p-1 min-w-24 align-top cursor-pointer hover:bg-pink-50/40"
                        >
                          <div className="w-full h-full pointer-events-none">
                            <ShiftCell shift={shift} />
                          </div>
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          ) : (
            <div className="overflow-x-auto">
              <table className="border-collapse bg-white rounded-xl border border-gray-200 text-[10px]" style={{ minWidth: "1100px" }}>
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200">
                    <th className="text-left px-3 py-2 text-[9px] font-semibold text-gray-500 border-r border-gray-200 w-36">
                      員工
                    </th>
                    {Array.from({ length: 31 }, (_, i) => (
                      <th key={i} className="px-0.5 py-2 text-[9px] text-gray-400 text-center border-r border-gray-100 w-8">
                        {i + 1}
                      </th>
                    ))}
                  </tr>
                </thead>

                <tbody>
                  {STAFF.map(s => {
                    const shiftTypes = ["A", "B", "E", "P", "A/N", "AL", "OFF", "SLEEP", "A", "B", "P", "OFF", "A/N", "AL", "E", "P", "OFF", "SLEEP", "A", "P", "B", "E", "AL", "OFF", "A/N", "P", "E", "B", "SLEEP", "OFF", "AL"]
                    return (
                      <tr key={s.id} className="border-t border-gray-100 hover:bg-pink-50/20">
                        <td className="px-2.5 py-1.5 border-r border-gray-200 bg-gray-50">
                          <div className="font-semibold text-gray-900 truncate">{s.nameEn.split(" ").slice(-1)[0]}</div>
                          <div className="text-gray-400 text-[8px]">
                            {s.role} · {s.floor}
                          </div>
                        </td>

                        {shiftTypes.map((t, i) => {
                          const cfg: { [k: string]: { bg: string; color: string } } = {
                            A: { bg: "#dbeafe", color: "#1d4ed8" },
                            B: { bg: "#e0f2fe", color: "#2563eb" },
                            E: { bg: "#dcfce7", color: "#15803d" },
                            P: { bg: "#d1fae5", color: "#047857" },
                            "A/N": { bg: "#ede9fe", color: "#6d28d9" },
                            AL: { bg: "#fef3c7", color: "#b45309" },
                            OFF: { bg: "#f3f4f6", color: "#6b7280" },
                            SLEEP: { bg: "#ede9fe", color: "#7c3aed" },
                          }
                          const c = cfg[t] || cfg.OFF
                          return (
                            <td
                              key={i}
                              className="px-0.5 py-1 text-center border-r border-gray-50 cursor-pointer"
                              onClick={() => {
                                setEditingShift({
                                  staffId: s.id,
                                  dayIndex: i,
                                  shiftType: t,
                                  tasks: [],
                                })
                                setShiftOpen(true)
                              }}
                            >
                              <span
                                className="inline-block min-w-[22px] h-4 rounded text-[8px] font-bold leading-4 text-center px-1"
                                style={{ background: c.bg, color: c.color }}
                              >
                                {t}
                              </span>
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

        {(showSaveList || showPublishList) && (
          <div className="border-l border-gray-200 bg-white overflow-auto xl:min-w-[340px]">
            {showSaveList && (
              <div className="p-4 border-b border-gray-100">
                <h3 className="text-sm font-bold text-gray-900 mb-2">Save List</h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {saveList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      暫時沒有未發布變更
                    </div>
                  ) : (
                    saveList.map(item => (
                      <div key={item.id} className="rounded-xl border border-pink-100 bg-pink-50/50 p-3">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-pink-600">{item.title}</span>
                          <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                        </div>
                        <div className="text-[11px] text-gray-600">{item.subtitle}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {showPublishList && (
              <div className="p-4">
                <h3 className="text-sm font-bold text-gray-900 mb-2">Publish List</h3>
                <div className="space-y-2 max-h-96 overflow-auto">
                  {publishList.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-gray-200 p-4 text-xs text-gray-400 text-center">
                      尚未有已發布紀錄
                    </div>
                  ) : (
                    publishList.map(item => (
                      <div key={item.id} className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-3">
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <span className="text-xs font-semibold text-emerald-700">{item.title}</span>
                          <span className="text-[10px] text-gray-400">{item.createdAt}</span>
                        </div>
                        <div className="text-[11px] text-gray-600">{item.subtitle}</div>
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
        onClose={() => {
          setShiftOpen(false)
          setEditingShift(null)
        }}
        mode={editingShift ? "edit" : "create"}
        initialShift={editingShift}
        onSaveChange={(payload: { shiftType: string }) => {
          const staffName = editingShift ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn || "員工" : "新更期"
          addSaveItem(
            editingShift ? "修改更期" : "新增更期",
            `${staffName} · ${payload.shiftType}`,
            editingShift ? "edit" : "create"
          )
          setShiftOpen(false)
          setEditingShift(null)
        }}
        onDeleteShift={() => {
          const staffName = editingShift ? STAFF.find(s => s.id === editingShift.staffId)?.nameEn || "員工" : "員工"
          addSaveItem("刪除更期", `${staffName} · ${editingShift?.shiftType || "shift"}`, "delete")
          setShiftOpen(false)
          setEditingShift(null)
        }}
      />

      <CreateEventModal open={eventOpen} onClose={() => setEventOpen(false)} />
    </div>
  )
}