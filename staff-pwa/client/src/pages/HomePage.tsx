/** Clinical Warmth: live personal dashboard; never invent operational data. */
/**
 * Clinical Warmth home: operational data stays quiet and focused while the
 * latest live alert comes from the shared attention channel.
 */
import { useEffect, useState } from "react";
import { useLocation } from "wouter";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { motion } from "framer-motion";
import { CheckCircle2, Clock, Calendar, Settings2, Bell, RefreshCw } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { getMyProfile, getMyRoster, getMyTasks, type RosterDay, type StaffProfile, type StaffTask } from "@/lib/api";
import { useAttention } from "@/contexts/AttentionContext";

const isoDate = (date: Date) => date.toISOString().slice(0, 10);
const addDays = (date: Date, days: number) => { const next = new Date(date); next.setDate(next.getDate() + days); return next; };
const shiftClass: Record<string, string> = {
  A: "bg-pink-100 text-pink-700 border-pink-200 dark:bg-pink-950/60 dark:text-pink-200 dark:border-pink-900", P: "bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-950/60 dark:text-rose-200 dark:border-rose-900", N: "bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-200 dark:border-indigo-900",
};

export default function HomePage() {
  const { user } = useAuth();
  const { latestNotification: latest } = useAttention();
  const [, setLocation] = useLocation();
  const [profile, setProfile] = useState<StaffProfile | null>(null);
  const [tasks, setTasks] = useState<StaffTask[]>([]);
  const [roster, setRoster] = useState<RosterDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true); setError("");
    const today = new Date();
    const results = await Promise.allSettled([
      getMyProfile(), getMyTasks(isoDate(today)), getMyRoster(isoDate(today), isoDate(addDays(today, 6))),
    ]);
    if (results[0].status === "fulfilled") setProfile(results[0].value);
    if (results[1].status === "fulfilled") setTasks(results[1].value);
    if (results[2].status === "fulfilled") setRoster(results[2].value.days);
    if (results.every((result) => result.status === "rejected")) setError("暫時未能載入個人資料，請稍後重試");
    setLoading(false);
  };

  useEffect(() => {
    void load();
    const refresh = () => { void load(); };
    window.addEventListener("emma:staff-data-invalidated", refresh);
    return () => window.removeEventListener("emma:staff-data-invalidated", refresh);
  }, []);
  const completed = tasks.filter((task) => task.status === "done").length;
  const progress = tasks.length ? (completed / tasks.length) * 100 : 0;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">你好，{profile?.name || user?.email?.split("@")[0] || "同事"}</h1>
          <p className="text-sm text-muted-foreground">{profile ? `${profile.rank}${profile.unit_name ? ` · ${profile.unit_name}` : ""}` : new Date().toLocaleDateString("zh-HK", { weekday: "long", month: "long", day: "numeric" })}</p>
        </div>
        <button onClick={() => setLocation("/preferences")} className="w-9 h-9 rounded-full flex items-center justify-center hover:bg-muted active:scale-95" aria-label="偏好設定"><Settings2 size={20} className="text-muted-foreground" /></button>
      </div>

      {error && <Card className="border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/60"><CardContent className="p-3 flex items-center justify-between"><p className="text-xs text-red-700 dark:text-red-200">{error}</p><button onClick={load}><RefreshCw size={15} className="text-red-700 dark:text-red-200" /></button></CardContent></Card>}

      <Card className="border-0 shadow-md shadow-coral/5"><CardContent className="p-4">
        <div className="flex items-center justify-between mb-3"><h2 className="font-semibold text-sm">今日任務進度</h2><Badge variant="secondary" className="font-mono text-xs">{completed}/{tasks.length}</Badge></div>
        <Progress value={progress} className="h-2.5 bg-muted [&>div]:bg-coral" />
        <p className="text-[13px] text-muted-foreground mt-2">{loading ? "從院舍系統載入中" : tasks.length ? `尚餘 ${tasks.length - completed} 項任務` : "今日暫未有已發佈任務"}</p>
      </CardContent></Card>

      {latest && <Card className="border border-border bg-card text-card-foreground shadow-sm cursor-pointer active:scale-[0.98]" onClick={() => setLocation("/messages")}><CardContent className="p-3 flex items-center gap-3"><div className="w-8 h-8 rounded-full bg-coral/10 flex items-center justify-center"><Bell size={15} className="text-coral" /></div><div className="flex-1 min-w-0"><p className="text-[13px] font-semibold truncate">{latest.title}</p><p className="text-xs text-muted-foreground truncate">{latest.body}</p></div></CardContent></Card>}

      <div><h2 className="font-semibold text-sm mb-2 flex items-center gap-1.5"><Calendar size={14} className="text-coral" />未來 7 日</h2><div className="flex gap-2 overflow-x-auto pb-1">
        {roster.map((day, index) => <div key={day.date} className={`shrink-0 w-14 rounded-xl border p-2 flex flex-col items-center gap-1 ${shiftClass[day.shift_type || ""] || "bg-muted/40 text-muted-foreground border-border"} ${index === 0 ? "ring-2 ring-coral ring-offset-1 ring-offset-background" : ""}`}><span className="text-xs opacity-70">{new Date(`${day.date}T00:00:00`).toLocaleDateString("zh-HK", { weekday: "short" })}</span><span className="font-mono text-xs font-bold">{day.shift_type || "—"}</span><span className="text-xs opacity-60">{day.date.slice(8)}</span></div>)}
        {!loading && roster.length === 0 && <p className="text-xs text-muted-foreground py-3">暫未有更表資料</p>}
      </div></div>

      <div><h2 className="font-semibold text-sm mb-2 flex items-center gap-1.5"><Clock size={14} className="text-rose-500" />今日工作</h2><div className="space-y-2">
        {tasks.slice(0, 5).map((task) => <Card key={task.id} className={`border-0 shadow-sm ${task.status === "done" ? "opacity-60" : ""}`}><CardContent className="p-3 flex items-center gap-3"><div className={`w-8 h-8 rounded-full flex items-center justify-center ${task.status === "done" ? "bg-emerald-100" : "bg-muted"}`}>{task.status === "done" ? <CheckCircle2 size={16} className="text-emerald-600" /> : <Clock size={16} className="text-rose-500" />}</div><p className="text-sm font-medium flex-1 truncate">{task.task_label}</p><span className="font-mono text-xs text-muted-foreground">{task.scheduled_time?.slice(0, 5) || "—"}</span></CardContent></Card>)}
      </div></div>

      {profile?.hours && <Card className="border-0 shadow-sm"><CardContent className="p-3"><div className="flex justify-between text-xs"><span className="text-muted-foreground">本期排更時數</span><span className="font-mono font-semibold">{profile.hours.scheduled_hours ?? 0} / {profile.hours.contracted_hours ?? 0}h</span></div></CardContent></Card>}
    </motion.div>
  );
}
