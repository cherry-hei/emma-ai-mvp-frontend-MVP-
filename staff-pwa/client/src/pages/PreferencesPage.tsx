import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { motion } from "framer-motion";
import { Settings2, Heart, Moon, Sun, Calendar, Plus, Trash2, Save, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { DisplaySettingsCard } from "@/components/DisplaySettingsCard";

// ─── Types ──────────────────────────────────────────────────────────────────
interface ShiftPreference {
  id: string;
  shiftCode: string;
  preference: "prefer" | "avoid";
  reason: string;
}

interface DayPreference {
  id: string;
  dayOfWeek: number; // 0=Mon, 6=Sun
  preference: "prefer_off" | "prefer_work" | "avoid_night";
  reason: string;
}

interface GeneralPreference {
  maxConsecutiveDays: number;
  preferMorning: boolean;
  preferAfternoon: boolean;
  preferNight: boolean;
  avoidWeekendNight: boolean;
  preferFixedPattern: boolean;
  notes: string;
}

// ─── Demo Data ──────────────────────────────────────────────────────────────
const DEMO_SHIFT_PREFS: ShiftPreference[] = [
  { id: "1", shiftCode: "A7", preference: "prefer", reason: "方便接小朋友放學" },
  { id: "2", shiftCode: "N", preference: "avoid", reason: "睡眠質素差" },
];

const DEMO_DAY_PREFS: DayPreference[] = [
  { id: "1", dayOfWeek: 6, preference: "prefer_off", reason: "星期日想陪家人" },
  { id: "2", dayOfWeek: 5, preference: "avoid_night", reason: "星期六晚想休息" },
];

const DEMO_GENERAL: GeneralPreference = {
  maxConsecutiveDays: 5,
  preferMorning: true,
  preferAfternoon: false,
  preferNight: false,
  avoidWeekendNight: true,
  preferFixedPattern: true,
  notes: "如果可以，希望每個cycle有相似嘅pattern",
};

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
const SHIFT_CODES = ["A7", "A230", "A1030", "P2", "P230", "AN", "N", "K10", "B930"];

// ─── Main Component ─────────────────────────────────────────────────────────
export default function PreferencesPage() {
  const [shiftPrefs, setShiftPrefs] = useState<ShiftPreference[]>(DEMO_SHIFT_PREFS);
  const [dayPrefs, setDayPrefs] = useState<DayPreference[]>(DEMO_DAY_PREFS);
  const [general, setGeneral] = useState<GeneralPreference>(DEMO_GENERAL);
  const [showAddShift, setShowAddShift] = useState(false);
  const [showAddDay, setShowAddDay] = useState(false);
  const [saved, setSaved] = useState(false);

  // Add shift form
  const [newShiftCode, setNewShiftCode] = useState("");
  const [newShiftPref, setNewShiftPref] = useState<"prefer" | "avoid">("prefer");
  const [newShiftReason, setNewShiftReason] = useState("");

  // Add day form
  const [newDay, setNewDay] = useState("0");
  const [newDayPref, setNewDayPref] = useState<"prefer_off" | "prefer_work" | "avoid_night">("prefer_off");
  const [newDayReason, setNewDayReason] = useState("");

  const handleAddShift = () => {
    if (!newShiftCode) return;
    setShiftPrefs([...shiftPrefs, {
      id: Date.now().toString(),
      shiftCode: newShiftCode,
      preference: newShiftPref,
      reason: newShiftReason,
    }]);
    setNewShiftCode("");
    setNewShiftReason("");
    setShowAddShift(false);
  };

  const handleAddDay = () => {
    setDayPrefs([...dayPrefs, {
      id: Date.now().toString(),
      dayOfWeek: parseInt(newDay),
      preference: newDayPref,
      reason: newDayReason,
    }]);
    setNewDayReason("");
    setShowAddDay(false);
  };

  const handleSave = () => {
    setSaved(true);
    toast.warning("排班偏好目前只係本機示範，未同步後端或排班引擎；顯示設定另會在本機保存。 ");
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <DisplaySettingsCard />
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
          <Settings2 size={18} className="text-coral" />
          個人偏好
        </h1>
        <Badge variant="secondary" className="text-xs">Soft Constraint</Badge>
      </div>

      <p className="text-[13px] text-muted-foreground leading-relaxed">
        下列排班偏好仍是<span className="font-semibold">未接後端的示範表單</span>，請勿當成已提交或已生效規則。
        已批准嘅假期（Hard Constraint）需要由真實審批流程處理。
      </p>

      {/* General Preferences */}
      <Card className="border-0 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Heart size={14} className="text-coral" />
            一般偏好
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Time preference */}
          <div className="space-y-2">
            <Label className="text-xs font-medium">偏好時段</Label>
            <div className="flex gap-3">
              <label className="flex items-center gap-2 text-xs">
                <Switch
                  checked={general.preferMorning}
                  onCheckedChange={(v) => setGeneral({ ...general, preferMorning: v })}
                />
                <Sun size={12} className="text-pink-500" />
                早更
              </label>
              <label className="flex items-center gap-2 text-xs">
                <Switch
                  checked={general.preferAfternoon}
                  onCheckedChange={(v) => setGeneral({ ...general, preferAfternoon: v })}
                />
                <Sun size={12} className="text-orange-500" />
                午更
              </label>
              <label className="flex items-center gap-2 text-xs">
                <Switch
                  checked={general.preferNight}
                  onCheckedChange={(v) => setGeneral({ ...general, preferNight: v })}
                />
                <Moon size={12} className="text-indigo-500" />
                夜更
              </label>
            </div>
          </div>

          {/* Max consecutive */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">希望連續工作日上限</Label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={1}
                max={6}
                value={general.maxConsecutiveDays}
                onChange={(e) => setGeneral({ ...general, maxConsecutiveDays: parseInt(e.target.value) || 5 })}
                className="h-9 w-20 text-center"
              />
              <span className="text-xs text-muted-foreground">日</span>
            </div>
          </div>

          {/* Other toggles */}
          <div className="space-y-2">
            <label className="flex items-center justify-between">
              <span className="text-xs">避免週末夜更</span>
              <Switch
                checked={general.avoidWeekendNight}
                onCheckedChange={(v) => setGeneral({ ...general, avoidWeekendNight: v })}
              />
            </label>
            <label className="flex items-center justify-between">
              <span className="text-xs">偏好固定更期模式</span>
              <Switch
                checked={general.preferFixedPattern}
                onCheckedChange={(v) => setGeneral({ ...general, preferFixedPattern: v })}
              />
            </label>
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">其他備註</Label>
            <Input
              value={general.notes}
              onChange={(e) => setGeneral({ ...general, notes: e.target.value })}
              placeholder="任何想讓排班系統知道嘅事..."
              className="h-9 text-xs"
            />
          </div>
        </CardContent>
      </Card>

      {/* Shift Preferences */}
      <Card className="border-0 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Calendar size={14} className="text-coral" />
            更期偏好
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {shiftPrefs.map((pref) => (
            <div key={pref.id} className="flex items-center gap-2 p-2 bg-muted/30 rounded-lg">
              <Badge variant={pref.preference === "prefer" ? "default" : "destructive"} className="text-xs h-5">
                {pref.preference === "prefer" ? "偏好" : "避免"}
              </Badge>
              <span className="text-xs font-mono font-semibold">{pref.shiftCode}</span>
              <span className="text-[13px] text-muted-foreground flex-1">{pref.reason}</span>
              <button onClick={() => setShiftPrefs(shiftPrefs.filter((p) => p.id !== pref.id))}>
                <Trash2 size={12} className="text-muted-foreground hover:text-red-500" />
              </button>
            </div>
          ))}

          {showAddShift ? (
            <div className="space-y-2 p-2 border border-dashed border-border rounded-lg">
              <div className="grid grid-cols-2 gap-2">
                <Select value={newShiftCode} onValueChange={setNewShiftCode}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="選擇更期" />
                  </SelectTrigger>
                  <SelectContent>
                    {SHIFT_CODES.map((code) => (
                      <SelectItem key={code} value={code}>{code}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={newShiftPref} onValueChange={(v) => setNewShiftPref(v as "prefer" | "avoid")}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="prefer">偏好</SelectItem>
                    <SelectItem value="avoid">避免</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Input
                value={newShiftReason}
                onChange={(e) => setNewShiftReason(e.target.value)}
                placeholder="原因（選填）"
                className="h-8 text-xs"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={handleAddShift} className="h-8 text-xs bg-coral hover:bg-coral-dark text-white">確認</Button>
                <Button size="sm" variant="ghost" onClick={() => setShowAddShift(false)} className="h-8 text-xs">取消</Button>
              </div>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setShowAddShift(true)} className="h-8 text-xs w-full">
              <Plus size={12} className="mr-1" /> 新增更期偏好
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Day Preferences */}
      <Card className="border-0 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Calendar size={14} className="text-coral" />
            星期偏好
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {dayPrefs.map((pref) => (
            <div key={pref.id} className="flex items-center gap-2 p-2 bg-muted/30 rounded-lg">
              <Badge variant="outline" className="text-xs h-5">
                星期{WEEKDAYS[pref.dayOfWeek]}
              </Badge>
              <Badge variant={pref.preference === "prefer_off" ? "secondary" : pref.preference === "avoid_night" ? "destructive" : "default"} className="text-xs h-5">
                {pref.preference === "prefer_off" ? "想休息" : pref.preference === "avoid_night" ? "避免夜更" : "想返工"}
              </Badge>
              <span className="text-[13px] text-muted-foreground flex-1">{pref.reason}</span>
              <button onClick={() => setDayPrefs(dayPrefs.filter((p) => p.id !== pref.id))}>
                <Trash2 size={12} className="text-muted-foreground hover:text-red-500" />
              </button>
            </div>
          ))}

          {showAddDay ? (
            <div className="space-y-2 p-2 border border-dashed border-border rounded-lg">
              <div className="grid grid-cols-2 gap-2">
                <Select value={newDay} onValueChange={setNewDay}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {WEEKDAYS.map((day, i) => (
                      <SelectItem key={i} value={i.toString()}>星期{day}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={newDayPref} onValueChange={(v) => setNewDayPref(v as typeof newDayPref)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="prefer_off">想休息</SelectItem>
                    <SelectItem value="prefer_work">想返工</SelectItem>
                    <SelectItem value="avoid_night">避免夜更</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Input
                value={newDayReason}
                onChange={(e) => setNewDayReason(e.target.value)}
                placeholder="原因（選填）"
                className="h-8 text-xs"
              />
              <div className="flex gap-2">
                <Button size="sm" onClick={handleAddDay} className="h-8 text-xs bg-coral hover:bg-coral-dark text-white">確認</Button>
                <Button size="sm" variant="ghost" onClick={() => setShowAddDay(false)} className="h-8 text-xs">取消</Button>
              </div>
            </div>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setShowAddDay(true)} className="h-8 text-xs w-full">
              <Plus size={12} className="mr-1" /> 新增星期偏好
            </Button>
          )}
        </CardContent>
      </Card>

      {/* Save Button */}
      <Button onClick={handleSave} className={`w-full h-11 font-semibold transition-all duration-300 ${saved ? "bg-emerald-500 hover:bg-emerald-600" : "bg-coral hover:bg-coral-dark"} text-white`}>
        {saved ? (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
            className="flex items-center gap-2"
          >
            <CheckCircle2 size={16} />
            本機示範 ✓
          </motion.span>
        ) : (
          <>
            <Save size={14} className="mr-2" />
            示範儲存（不會提交）
          </>
        )}
      </Button>

      <p className="text-xs text-center text-muted-foreground">
        此頁的排班偏好尚未連接排班引擎。如需強制要求（如醫療原因不做夜更），請聯絡院長；切勿在非香港試用系統輸入真實醫療資料。
      </p>
    </motion.div>
  );
}
