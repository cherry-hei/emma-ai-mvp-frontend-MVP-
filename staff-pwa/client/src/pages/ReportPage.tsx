import { useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { motion } from "framer-motion";
import { FileText, Upload, Send, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { submitLeaveRequest } from "@/lib/api";
import { staffApiFeatures } from "@/lib/features";

export default function ReportPage() {
  const submitting = useRef(false);
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [leaveType, setLeaveType] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leaveType || !startDate || !reason) {
      toast.error("請填寫所有必填欄位");
      return;
    }
    if (submitting.current) return;
    submitting.current = true;
    setSaving(true);
    try {
      await submitLeaveRequest({ leave_type: leaveType, date_start: startDate, date_end: endDate || startDate, reason });
      setSubmitted(true);
      toast.success("申請已提交，等待獲授權主管審批");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "提交失敗；草稿已保留");
    } finally {
      submitting.current = false;
      setSaving(false);
    }
  };

  if (submitted) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="flex flex-col items-center justify-center py-16 text-center"
      >
        <div className="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mb-4">
          <CheckCircle2 size={32} className="text-emerald-600" />
        </div>
        <h2 className="text-lg font-bold text-foreground">申請已提交</h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-[250px]">
          你的申請已發送至院長審批頁面，批核後會收到通知。
        </p>
        <Button
          onClick={() => { setSubmitted(false); setLeaveType(""); setStartDate(""); setEndDate(""); setReason(""); }}
          variant="outline"
          className="mt-6"
        >
          提交新申請
        </Button>
      </motion.div>
    );
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
        <FileText size={18} className="text-rose-500" />
        請假 / 報告
      </h1>

      <Card className="border-0 shadow-md">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold">提交申請</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <fieldset disabled={saving} className="space-y-4">
            {/* Leave Type */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">申請類型 *</Label>
              <Select value={leaveType} onValueChange={setLeaveType}>
                <SelectTrigger className="h-11">
                  <SelectValue placeholder="選擇類型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="SL">病假 (Sick Leave)</SelectItem>
                  <SelectItem value="AL">年假 (Annual Leave)</SelectItem>
                  <SelectItem value="CL">恩恤假 (Compassionate)</SelectItem>
                  <SelectItem value="DSL">緊急病假 (Emergency SL)</SelectItem>
                  <SelectItem disabled={!staffApiFeatures.dutyRequestWindow.available} value="DO">調假 (Day Off Request)</SelectItem>
                  <SelectItem disabled={!staffApiFeatures.dutyRequestWindow.available} value="duty_request">更期要求 (Duty Request)</SelectItem>
                  <SelectItem disabled={!staffApiFeatures.dutyRequestWindow.available} value="shift_swap">調更 (Shift Swap)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Dates */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">開始日期 *</Label>
                <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="h-11" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">結束日期</Label>
                <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="h-11" />
              </div>
            </div>

            {/* Reason */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">原因 *</Label>
              <Textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="請簡述原因..."
                rows={3}
              />
            </div>

            {/* File Upload */}
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">附件（醫生紙等）</Label>
              <div className="border-2 border-dashed border-border rounded-xl p-4 text-center transition-colors">
                <Upload size={20} className="mx-auto text-muted-foreground mb-1" />
                <p className="text-xs text-muted-foreground">附件上傳尚未開放；請按院舍程序提交文件</p>
              </div>
            </div>

            {/* Submit */}
            <Button type="submit" className="w-full h-11 bg-coral hover:bg-coral-dark text-white font-semibold">
              <Send size={16} className="mr-1.5" />
              提交申請
            </Button>
            </fieldset>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
