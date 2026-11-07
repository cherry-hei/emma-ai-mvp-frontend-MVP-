/** Clinical Warmth: exact live roster dates, no generated shifts or synthetic fill. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, CalendarPlus, Clock, X, RefreshCw } from "lucide-react";
import { getMyRoster, type RosterDay } from "@/lib/api";
import { staffApiFeatures } from "@/lib/features";

const SHIFT_BG: Record<string, string> = { A: "bg-pink-100 text-pink-800 dark:bg-pink-950/70 dark:text-pink-200", P: "bg-rose-100 text-rose-700 dark:bg-rose-950/70 dark:text-rose-200", N: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950/70 dark:text-indigo-200", DO: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-200", AL: "bg-green-100 text-green-800 dark:bg-green-950/70 dark:text-green-200", SL: "bg-muted text-muted-foreground", CL: "bg-teal-100 text-teal-800 dark:bg-teal-950/70 dark:text-teal-200" };
const WEEKDAY_LABELS = ["日", "一", "二", "三", "四", "五", "六"];
const iso = (year: number, month: number, day: number) => `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;

export default function RosterPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth());
  const [days, setDays] = useState<RosterDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState<RosterDay | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [, setLocation] = useLocation();

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const end = new Date(year, month + 1, 0).getDate(); setDays((await getMyRoster(iso(year, month, 1), iso(year, month, end))).days); }
    catch (err) { setError(err instanceof Error ? err.message : "未能載入更表"); setDays([]); }
    finally { setLoading(false); }
  }, [year, month]);
  useEffect(() => {
    void load();
    const refresh = () => { void load(); };
    window.addEventListener("emma:staff-data-invalidated", refresh);
    return () => window.removeEventListener("emma:staff-data-invalidated", refresh);
  }, [load]);
  const byDate = useMemo(() => new Map(days.map((day) => [day.date, day])), [days]);
  const first = new Date(year, month, 1).getDay();
  const count = new Date(year, month + 1, 0).getDate();
  const cells: Array<RosterDay | null> = Array.from({ length: first }, () => null);
  for (let day = 1; day <= count; day++) cells.push(byDate.get(iso(year, month, day)) || { date: iso(year, month, day), shift_type: null, is_working: false, tasks: [] });
  const startPress = useCallback((day: RosterDay) => { timer.current = setTimeout(() => setAction(day), 500); }, []);
  const endPress = useCallback(() => { if (timer.current) clearTimeout(timer.current); timer.current = null; }, []);
  const change = (delta: number) => { const next = new Date(year, month + delta, 1); setYear(next.getFullYear()); setMonth(next.getMonth()); };

  return <div className="space-y-3"><div className="flex items-center justify-between"><h1 className="text-lg font-bold">我的更表</h1>{error && <button onClick={load}><RefreshCw size={16} className="text-red-600" /></button>}</div>
    <div className="flex items-center justify-between"><Button variant="ghost" size="icon" onClick={() => change(-1)}><ChevronLeft size={18} /></Button><span className="font-semibold text-sm">{year}年{month + 1}月</span><Button variant="ghost" size="icon" onClick={() => change(1)}><ChevronRight size={18} /></Button></div>
    {error && <p className="text-xs text-red-700 bg-red-50 p-2 rounded-lg dark:bg-red-950/60 dark:text-red-200">{error}</p>}
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-xl border border-border bg-card text-card-foreground shadow-sm p-2"><div className="grid grid-cols-7 mb-1">{WEEKDAY_LABELS.map((label) => <div key={label} className="text-center text-xs text-muted-foreground py-1">{label}</div>)}</div><div className="grid grid-cols-7 gap-1">{cells.map((day, index) => !day ? <div key={`blank-${index}`} className="aspect-square" /> : <div key={day.date} onTouchStart={() => startPress(day)} onTouchEnd={endPress} onMouseDown={() => startPress(day)} onMouseUp={endPress} onMouseLeave={endPress} className={`aspect-square rounded-lg flex flex-col items-center justify-center gap-0.5 select-none ${day.date === now.toISOString().slice(0, 10) ? "ring-2 ring-coral ring-offset-1 ring-offset-background" : ""} ${day.shift_type ? SHIFT_BG[day.shift_type] || "bg-muted text-muted-foreground" : "bg-muted/35 text-muted-foreground"}`}><span className="text-xs font-medium">{day.date.slice(8)}</span><span className="font-mono text-xs font-bold">{day.shift_type || "—"}</span></div>)}</div></motion.div>
    <p className="text-xs text-center text-muted-foreground">{loading ? "從院舍系統載入中…" : "長按日期可快速申請假期或指定更期"}</p>
    <div className="flex flex-wrap gap-2 px-1">{Object.entries({ A: "早更", P: "午更", N: "夜更", AL: "年假", SL: "病假", CL: "補假" }).map(([type, label]) => <div key={type} className="flex items-center gap-1"><div className={`w-3 h-3 rounded-sm ${SHIFT_BG[type]}`} /><span className="text-xs text-muted-foreground">{label}</span></div>)}</div>
    <AnimatePresence>{action && <><motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/30 z-50" onClick={() => setAction(null)} /><motion.div initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} className="fixed bottom-0 left-0 right-0 max-w-md mx-auto rounded-t-2xl border border-border bg-card text-card-foreground z-50 p-4 pb-8"><div className="flex justify-between mb-4"><div><p className="text-sm font-semibold">{action.date}</p><p className="text-xs text-muted-foreground">目前排班：{action.shift_type || "未排班"}</p></div><button onClick={() => setAction(null)}><X size={18} /></button></div><div className="space-y-2"><button onClick={() => setLocation(`/records?action=leave&date=${action.date}`)} className="w-full flex items-center gap-3 p-3 rounded-xl bg-pink-50 dark:bg-pink-950/40"><CalendarPlus size={18} className="text-coral" /><div className="text-left"><p className="text-sm font-semibold">申請假期</p><p className="text-xs text-muted-foreground">日期會自動填入申請表</p></div></button><div className="w-full rounded-xl bg-muted/60 p-3"><div className="flex items-center gap-3"><Clock size={18} className="text-muted-foreground" /><div className="text-left"><p className="text-sm font-semibold">指定更期暫未開放</p><p className="text-xs text-muted-foreground">{staffApiFeatures.dutyRequestWindow.unavailableMessage}</p></div></div></div></div></motion.div></>}</AnimatePresence>
  </div>;
}
