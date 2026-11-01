import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { motion } from "framer-motion";
import { Award, Plus, AlertTriangle, CheckCircle2, Clock, Upload } from "lucide-react";
import { toast } from "sonner";

interface Cert {
  id: string;
  name: string;
  cert_number: string;
  issue_date: string;
  expiry_date: string;
  status: "valid" | "expiring_soon" | "expired";
}

const DEMO_CERTS: Cert[] = [
  { id: "1", name: "ACLS", cert_number: "ACLS-2024-HK-8821", issue_date: "2024-09-15", expiry_date: "2026-09-15", status: "expiring_soon" },
  { id: "2", name: "BLS", cert_number: "BLS-2025-HK-1102", issue_date: "2025-03-01", expiry_date: "2027-03-01", status: "valid" },
  { id: "3", name: "Triage Certificate", cert_number: "TRI-2023-HK-5567", issue_date: "2023-06-20", expiry_date: "2025-06-20", status: "expired" },
  { id: "4", name: "EN Registration", cert_number: "EN-HK-29834", issue_date: "2020-01-10", expiry_date: "2028-01-10", status: "valid" },
];

const STATUS_CONFIG = {
  valid: { icon: CheckCircle2, color: "text-emerald-600", bg: "bg-emerald-50", badge: "bg-emerald-100 text-emerald-700", label: "有效" },
  expiring_soon: { icon: Clock, color: "text-pink-600", bg: "bg-pink-50", badge: "bg-pink-100 text-pink-700", label: "即將到期" },
  expired: { icon: AlertTriangle, color: "text-red-500", bg: "bg-red-50", badge: "bg-red-100 text-red-700", label: "已過期" },
};

export default function CertsPage() {
  const [certs, setCerts] = useState(DEMO_CERTS);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newCert, setNewCert] = useState({ name: "", cert_number: "", issue_date: "", expiry_date: "" });

  const handleAdd = () => {
    if (!newCert.name || !newCert.cert_number || !newCert.expiry_date) {
      toast.error("請填寫所有必填欄位");
      return;
    }
    setCerts((prev) => [
      ...prev,
      { ...newCert, id: Date.now().toString(), status: "valid" as const },
    ]);
    setNewCert({ name: "", cert_number: "", issue_date: "", expiry_date: "" });
    setDialogOpen(false);
    toast.success("證書已新增，HR 將收到通知");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
          <Award size={18} className="text-coral" />
          我的證書
        </h1>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button size="sm" className="bg-coral hover:bg-coral-dark text-white h-8 text-xs">
              <Plus size={14} className="mr-1" />
              新增
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-[340px] rounded-2xl">
            <DialogHeader>
              <DialogTitle className="text-base">新增證書</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 mt-2">
              <div className="space-y-1.5">
                <Label className="text-xs">證書名稱 *</Label>
                <Input value={newCert.name} onChange={(e) => setNewCert({ ...newCert, name: e.target.value })} placeholder="如 ACLS, BLS..." className="h-10" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">證書編號 *</Label>
                <Input value={newCert.cert_number} onChange={(e) => setNewCert({ ...newCert, cert_number: e.target.value })} placeholder="ACLS-2024-HK-XXXX" className="h-10" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="space-y-1.5">
                  <Label className="text-xs">發出日期</Label>
                  <Input type="date" value={newCert.issue_date} onChange={(e) => setNewCert({ ...newCert, issue_date: e.target.value })} className="h-10" />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">到期日 *</Label>
                  <Input type="date" value={newCert.expiry_date} onChange={(e) => setNewCert({ ...newCert, expiry_date: e.target.value })} className="h-10" />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">上傳證書圖片</Label>
                <div className="border-2 border-dashed border-border rounded-xl p-3 text-center cursor-pointer hover:border-coral/40 transition-colors">
                  <Upload size={18} className="mx-auto text-muted-foreground mb-1" />
                  <p className="text-[11px] text-muted-foreground">點擊上傳</p>
                </div>
              </div>
              <Button onClick={handleAdd} className="w-full bg-coral hover:bg-coral-dark text-white h-10">
                儲存證書
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Cert Cards */}
      <div className="space-y-2">
        {certs.map((cert, i) => {
          const config = STATUS_CONFIG[cert.status];
          const Icon = config.icon;
          return (
            <motion.div
              key={cert.id}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <Card className={`border-0 shadow-sm ${config.bg}`}>
                <CardContent className="p-3">
                  <div className="flex items-start gap-3">
                    <div className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${config.bg}`}>
                      <Icon size={16} className={config.color} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-foreground">{cert.name}</p>
                        <Badge className={`text-[10px] px-1.5 py-0 border-0 ${config.badge}`}>
                          {config.label}
                        </Badge>
                      </div>
                      <p className="font-mono text-[11px] text-muted-foreground mt-0.5">{cert.cert_number}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        到期：{new Date(cert.expiry_date).toLocaleDateString("zh-HK")}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
