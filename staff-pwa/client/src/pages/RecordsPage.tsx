/** Staff-scoped request history. Request-window data is unavailable in the verified API contract. */
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FileText, Plus, RefreshCw, Info } from "lucide-react";
import { toast } from "sonner";
import { getMyLeaveRequests, submitLeaveRequest, withdrawLeaveRequest, type LeaveRequest } from "@/lib/api";
import { staffApiFeatures } from "@/lib/features";
import { filterRecordsByDateRange, isRecordDateRangeValid } from "@/lib/recordFilters";

const TYPES: Record<string, string> = {
  AL: "年假", SL: "病假", CL: "補假", DSL: "緊急病假",
};
const statusText = (value: string) =>
  ({ approved: "已批准 · Hard", rejected: "已拒絕", cancelled: "已撤回", reviewed: "審核中 · Soft", pending: "待審核 · Soft" } as Record<string, string>)[value] || value;

export default function RecordsPage() {
  const query = new URLSearchParams(window.location.search);
  const [records, setRecords] = useState<LeaveRequest[]>([]);
  const [showForm, setShowForm] = useState(Boolean(query.get("action")) && query.get("action") !== "duty");
  const [type, setType] = useState("");
  const [start, setStart] = useState(query.get("date") || "");
  const [end, setEnd] = useState(query.get("date") || "");
  const [reason, setReason] = useState("");
  const [filter, setFilter] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      // /me/leave-requests is user-bound. The live contract has no date query
      // here, so filtering happens locally without switching to a broader list.
      setRecords(await getMyLeaveRequests());
      setError("");
    } catch (event) {
      setError(event instanceof Error ? event.message : "未能載入紀錄");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void load();
    const refresh = () => { void load(); };
    window.addEventListener("emma:staff-data-invalidated", refresh);
    return () => window.removeEventListener("emma:staff-data-invalidated", refresh);
  }, []);

  const validRange = isRecordDateRangeValid({ from, to });
  const visible = useMemo(() => filterRecordsByDateRange(
    records.filter((record) => filter === "all" || record.status.toLowerCase() === filter),
    { from, to },
  ), [records, filter, from, to]);
  const canSubmit = !!type && !!start && (!end || end >= start);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return toast.error("請確認申請類型及日期");
    setSaving(true);
    try {
      await submitLeaveRequest({ leave_type: type, date_start: start, date_end: end || start, reason: reason.trim() || null });
      toast.success("申請已提交，等待主管審核；提交不等於批准。");
      setShowForm(false);
      setReason("");
      await load();
    } catch (event) {
      toast.error(event instanceof Error ? event.message : "提交失敗，未保存");
    } finally {
      setSaving(false);
    }
  }
  async function withdraw(id: string) {
    try {
      await withdrawLeaveRequest(id);
      toast.success("申請已撤回");
      await load();
    } catch (event) {
      toast.error(event instanceof Error ? event.message : "未能撤回");
    }
  }

  return <div className="space-y-4 text-foreground">
    <div className="flex items-center justify-between gap-2"><h1 className="flex items-center gap-2 text-lg font-bold"><FileText size={18} className="text-coral" />申請紀錄</h1><Button size="sm" onClick={() => setShowForm((value) => !value)} className="bg-coral text-white"><Plus size={14} className="mr-1" />新申請</Button></div>
    <p className="text-[13px] text-muted-foreground">已批准才成為硬性約束；待處理要求只是軟性，並不自動改更表。</p>
    <div className="flex gap-3 rounded-xl border border-border bg-muted/30 p-3 text-[13px] text-card-foreground"><Info size={17} className="mt-0.5 shrink-0 text-muted-foreground" /><p><strong>指定更期／休息日申請暫未開放。</strong>{staffApiFeatures.dutyRequestWindow.unavailableMessage}</p></div>
    {showForm && <Card className="border-0 shadow-sm"><CardHeader className="pb-2"><CardTitle className="text-sm">提交新申請</CardTitle></CardHeader><CardContent><form onSubmit={submit} className="space-y-3"><div><Label>類型 *</Label><Select value={type} onValueChange={setType}><SelectTrigger className="mt-1"><SelectValue placeholder="選擇類型" /></SelectTrigger><SelectContent>{Object.entries(TYPES).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></div><div className="grid grid-cols-2 gap-3"><div><Label>開始日期 *</Label><Input type="date" value={start} onChange={(event) => setStart(event.target.value)} className="mt-1" /></div><div><Label>結束日期</Label><Input type="date" value={end} onChange={(event) => setEnd(event.target.value)} className="mt-1" /></div></div><div><Label>原因</Label><Textarea value={reason} onChange={(event) => setReason(event.target.value)} rows={2} className="mt-1" /></div><p className="text-[13px] text-muted-foreground">附件上傳需待香港儲存服務確認；本表不會假裝已上載檔案。</p><Button type="submit" disabled={saving || !canSubmit} className="w-full bg-coral text-white">{saving ? "提交中…" : "提交申請"}</Button></form></CardContent></Card>}
    <div className="flex gap-2 overflow-x-auto">{[["all", "全部"], ["pending", "待審核"], ["reviewed", "已審閱"], ["approved", "已批准"], ["rejected", "已拒絕"]].map(([value, label]) => <button key={value} type="button" onClick={() => setFilter(value)} aria-pressed={filter === value} className={`shrink-0 rounded-full px-3 py-2 text-xs ${filter === value ? "bg-coral text-white" : "bg-muted text-muted-foreground"}`}>{label}</button>)}</div>
    <div className="grid grid-cols-2 gap-2"><div><Label>由</Label><Input aria-label="紀錄由日期" type="date" value={from} onChange={(event) => setFrom(event.target.value)} /></div><div><Label>至</Label><Input aria-label="紀錄至日期" type="date" value={to} onChange={(event) => setTo(event.target.value)} /></div></div>
    {!validRange && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-100">開始日期不可遲於結束日期。</p>}
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-100">{error} <button onClick={() => void load()} aria-label="重新整理"><RefreshCw size={15} /></button></p>}
    {loading ? <p className="py-4 text-center text-sm">載入中…</p> : !visible.length ? <p className="py-8 text-center text-sm text-muted-foreground">沒有符合條件的申請。</p> : <div className="space-y-2">{visible.map((record) => <Card key={record.id} className="border-0 shadow-sm"><CardContent className="p-3 text-sm"><div className="flex justify-between gap-2"><strong>{TYPES[record.leave_type || ""] || record.leave_type || "申請"}</strong><Badge variant="secondary">{statusText(record.status)}</Badge></div><p className="mt-1 font-mono text-[13px] text-muted-foreground">{record.date_start} → {record.date_end}{record.requested_shift_type ? ` · ${record.requested_shift_type}` : ""}</p>{record.reason && <p className="mt-1 text-[13px] text-muted-foreground">{record.reason}</p>}{["pending", "reviewed"].includes(record.status.toLowerCase()) && <button type="button" onClick={() => void withdraw(record.id)} className="mt-2 text-xs text-red-700 dark:text-red-200">撤回申請</button>}</CardContent></Card>)}</div>}
  </div>;
}
