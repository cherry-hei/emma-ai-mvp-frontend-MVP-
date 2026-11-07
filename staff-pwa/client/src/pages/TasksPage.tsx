/** Clinical Warmth: real task assignments with deliberate, reversible status actions. */
import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { CheckCircle2, Clock, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { getMyTasks, updateMyTask, type StaffTask } from "@/lib/api";

const today = () => new Date().toISOString().slice(0, 10);

export default function TasksPage() {
  const [tasks, setTasks] = useState<StaffTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savingId, setSavingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true); setError("");
    try { setTasks(await getMyTasks(today())); }
    catch (err) { setError(err instanceof Error ? err.message : "未能載入任務"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const markDone = async (id: string) => {
    setSavingId(id);
    try { await updateMyTask(id, "done"); setTasks((prev) => prev.map((task) => task.id === id ? { ...task, status: "done" } : task)); toast.success("任務已標記完成"); }
    catch (err) { toast.error(err instanceof Error ? err.message : "更新失敗"); }
    finally { setSavingId(null); }
  };
  const pending = tasks.filter((task) => task.status !== "done");
  const done = tasks.filter((task) => task.status === "done");

  return <div className="space-y-4">
    <div className="flex items-center justify-between"><h1 className="text-lg font-bold">今日工作</h1><Badge variant="secondary" className="font-mono">{done.length}/{tasks.length} 完成</Badge></div>
    {error && <Card className="border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/60"><CardContent className="p-3 flex justify-between"><p className="text-xs text-red-700 dark:text-red-200">{error}</p><button onClick={load}><RefreshCw size={15} className="text-red-700 dark:text-red-200" /></button></CardContent></Card>}
    {loading && <p className="text-xs text-muted-foreground text-center py-8">載入已分配工作中…</p>}
    {!loading && !tasks.length && <Card className="border-0 shadow-sm"><CardContent className="py-10 text-center"><CheckCircle2 className="mx-auto text-emerald-500 mb-2" /><p className="text-sm font-medium">今日暫未有已分配工作</p><p className="text-xs text-muted-foreground mt-1">只會顯示後端已發佈給你的task assignment。</p></CardContent></Card>}
    <div className="space-y-2">{pending.map((task) => <motion.div key={task.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}><Card className="border-0 shadow-sm"><CardContent className="p-3"><div className="flex items-center gap-3"><div className="w-9 h-9 rounded-full bg-pink-50 flex items-center justify-center dark:bg-pink-950/40"><Clock size={16} className="text-coral" /></div><div className="flex-1 min-w-0"><p className="text-sm font-medium truncate">{task.task_label}</p><p className="text-[13px] text-muted-foreground font-mono">{task.scheduled_time?.slice(0, 5) || "未指定時間"}{task.shift_type ? ` · ${task.shift_type}更` : ""}</p></div><Button disabled={savingId === task.id} onClick={() => markDone(task.id)} size="sm" className="bg-emerald-500 hover:bg-emerald-600 text-white">完成</Button></div></CardContent></Card></motion.div>)}</div>
    {done.length > 0 && <div className="space-y-2"><h2 className="text-sm text-muted-foreground flex items-center gap-1.5"><CheckCircle2 size={14} className="text-emerald-500" />已完成 ({done.length})</h2>{done.map((task) => <Card key={task.id} className="border-0 shadow-sm opacity-55"><CardContent className="p-3 flex items-center gap-3"><CheckCircle2 size={18} className="text-emerald-500" /><p className="text-sm text-muted-foreground line-through truncate">{task.task_label}</p></CardContent></Card>)}</div>}
  </div>;
}
