/**
 * Notifications and replacement offers have verified staff API contracts.
 * Direct messages remain disabled until a reviewed backend contract exists.
 */
import { useMemo, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { motion } from "framer-motion";
import { MessageCircle, AlertTriangle, CheckCircle2, Search, RefreshCw, Bell, Info } from "lucide-react";
import { toast } from "sonner";
import { type ReplacementOffer, type StaffNotification } from "@/lib/api";
import { staffApiFeatures } from "@/lib/features";
import { useAttention } from "@/contexts/AttentionContext";

const offerStatus: Record<string, { label: string; style: string }> = {
  pending: { label: "等待回覆", style: "bg-pink-100 text-pink-800 dark:bg-pink-950/70 dark:text-pink-200" },
  accepted: { label: "已接受，等候主管", style: "bg-blue-100 text-blue-800 dark:bg-blue-950/70 dark:text-blue-200" },
  declined: { label: "已婉拒", style: "bg-muted text-muted-foreground" },
  approved: { label: "主管已批准", style: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/70 dark:text-emerald-200" },
  withdrawn: { label: "主管已撤回", style: "bg-muted text-muted-foreground" },
  superseded: { label: "已由其他同事接更", style: "bg-muted text-muted-foreground" },
};

export default function MessagesPage() {
  const { offers, notifications, loading, error, refresh, markRead, respondToOffer, connectionState, lastUpdatedAt } = useAttention();
  const [search, setSearch] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const answer = async (offer: ReplacementOffer, accept: boolean) => {
    setSaving(offer.id);
    try {
      await respondToOffer(offer, accept);
      toast.success(accept ? "已通知主管你願意接更；尚未正式排入更表" : "已向主管婉拒邀請");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "回覆失敗");
      await refresh();
    } finally {
      setSaving(null);
    }
  };
  const read = async (notification: StaffNotification) => {
    try {
      await markRead(notification);
    } catch {
      toast.error("暫時未能更新已讀狀態");
    }
  };
  const filteredOffers = useMemo(
    () => offers.filter((offer) => `${offer.note || ""} ${offer.rank_required || ""}`.toLowerCase().includes(search.toLowerCase())),
    [offers, search],
  );
  const filteredNotifications = useMemo(
    () => notifications.filter((item) => `${item.title} ${item.body}`.toLowerCase().includes(search.toLowerCase())),
    [notifications, search],
  );

  return <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
    <div className="flex items-center justify-between"><div><h1 className="flex items-center gap-2 text-lg font-bold"><MessageCircle size={18} className="text-coral" />通知與接更</h1><p className="mt-0.5 text-xs text-muted-foreground">{connectionState === "offline" ? "離線中，恢復網絡後自動更新" : lastUpdatedAt ? `最後更新 ${new Date(lastUpdatedAt).toLocaleTimeString("zh-HK", { hour: "2-digit", minute: "2-digit" })}` : "連接院舍通知中"}</p></div><button onClick={() => void refresh()} aria-label="重新整理" disabled={loading}><RefreshCw size={16} className={`text-muted-foreground ${loading ? "animate-spin" : ""}`} /></button></div>
    <div className="relative"><Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜尋通知或接更邀請…" className="h-9 rounded-full border-0 bg-muted/50 pl-9 text-xs" /></div>
    <Card className="border border-border bg-muted/30"><CardContent className="flex gap-3 p-3"><Info size={17} className="mt-0.5 shrink-0 text-muted-foreground" /><div><p className="text-sm font-semibold">院內直接訊息暫未開放</p><p className="mt-1 text-xs leading-relaxed text-muted-foreground">{staffApiFeatures.directMessages.unavailableMessage}</p></div></CardContent></Card>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-2 text-xs text-red-700 dark:bg-red-950/60 dark:text-red-200">{error}</p>}
    <section className="space-y-2"><div className="flex items-center justify-between"><h2 className="flex items-center gap-1.5 text-sm font-semibold"><AlertTriangle size={14} className="text-coral" />突發病假接更邀請</h2><Badge variant="secondary" className="text-xs">{offers.filter((offer) => offer.status === "pending").length} 待回覆</Badge></div>
      {!loading && !filteredOffers.length && <Card className="border-0 shadow-sm"><CardContent className="py-8 text-center"><p className="text-sm font-medium">暫未有接更邀請</p><p className="mt-1 text-xs text-muted-foreground">主管發出邀請後會顯示在此。</p></CardContent></Card>}
      {filteredOffers.map((offer) => { const meta = offerStatus[offer.status] || { label: offer.status, style: "bg-muted text-muted-foreground" }; return <Card key={offer.id} className="overflow-hidden border-0 shadow-sm"><CardContent className="p-4"><div className="flex justify-between gap-3"><div><p className="text-sm font-semibold">接更邀請</p><p className="mt-1 text-[13px] text-muted-foreground">{offer.note || "主管邀請你處理一個空缺更期"}</p></div><Badge className={`h-fit text-xs ${meta.style}`}>{meta.label}</Badge></div><div className="mt-3 grid grid-cols-2 gap-2 text-[13px]"><div className="rounded-lg bg-muted/50 p-2"><span className="text-muted-foreground">要求職級</span><p className="font-semibold">{offer.rank_required || "按資格審核"}</p></div><div className="rounded-lg bg-muted/50 p-2"><span className="text-muted-foreground">建議分數</span><p className="font-semibold">{offer.score ?? "—"}</p></div></div>{offer.status === "pending" && <div className="mt-3 flex gap-2"><Button disabled={saving === offer.id} onClick={() => void answer(offer, true)} className="flex-1 bg-emerald-500 text-white hover:bg-emerald-600">願意接更</Button><Button disabled={saving === offer.id} onClick={() => void answer(offer, false)} variant="outline" className="flex-1">未能接更</Button></div>}{offer.status === "accepted" && <p className="mt-3 rounded-lg bg-blue-50 p-2 text-xs text-blue-700 dark:bg-blue-950/60 dark:text-blue-200">已送交主管作最後批准；在主管批准前，更期不會加入你的更表。</p>}</CardContent></Card>; })}
    </section>
    <section className="space-y-2"><h2 className="flex items-center gap-1.5 text-sm font-semibold"><Bell size={14} className="text-coral" />系統通知</h2>{!loading && !filteredNotifications.length && <p className="py-5 text-center text-xs text-muted-foreground">暫未有系統通知</p>}{filteredNotifications.map((notification) => { const unread = notification.status !== "read" && !notification.read_at; return <Card key={notification.id} onClick={() => void read(notification)} className={`cursor-pointer border border-border shadow-sm ${unread ? "bg-pink-50/60 text-card-foreground dark:bg-pink-950/30" : "bg-card text-card-foreground"}`}><CardContent className="flex gap-3 p-3"><div className={`flex h-8 w-8 items-center justify-center rounded-full ${unread ? "bg-coral/10" : "bg-muted"}`}>{unread ? <Bell size={14} className="text-coral" /> : <CheckCircle2 size={14} className="text-muted-foreground" />}</div><div className="min-w-0 flex-1"><div className="flex justify-between gap-2"><p className="text-sm font-medium">{notification.title}</p><span className="text-xs text-muted-foreground">{new Date(notification.created_at).toLocaleDateString("zh-HK")}</span></div><p className="mt-1 text-xs text-muted-foreground">{notification.body}</p></div></CardContent></Card>; })}</section>
  </motion.div>;
}
