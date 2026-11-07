import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { motion } from "framer-motion";
import { Settings, Building2, UserCog, ToggleLeft, CalendarHeart, Heart, Plus, Trash2, Save, Users } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

// ─── Types ──────────────────────────────────────────────────────────────────
interface FacilityConfig {
  facilityName: string;
  facilityType: string;
  careLevel: string;
  residentCount: string;
  designatedPeriodStart: string;
  designatedPeriodEnd: string;
  specificHoursStart: string;
  specificHoursEnd: string;
  effectiveDate: string;
  expiryDate: string;
}

interface StaffConstraint {
  id: string;
  staffName: string;
  constraintType: string;
  detail: string;
  effectiveFrom: string;
}

interface ConstraintToggle {
  id: string;
  name: string;
  description: string;
  category: string;
  isHard: boolean;
}

interface SpecialEvent {
  id: string;
  name: string;
  requiredStaff: string;
  requiredRank: string;
  recurring: string;
}

interface PersonalPref {
  preferredShifts: string[];
  avoidShifts: string[];
  preferredDaysOff: string[];
  notes: string;
}

// ─── Demo Data ──────────────────────────────────────────────────────────────
const DEMO_FACILITY: FacilityConfig = {
  facilityName: "鄰舍輔導會大興宿舍",
  facilityType: "RCHD",
  careLevel: "medium",
  residentCount: "60",
  designatedPeriodStart: "06:00",
  designatedPeriodEnd: "22:00",
  specificHoursStart: "10:00",
  specificHoursEnd: "16:00",
  effectiveDate: "2024-06-16",
  expiryDate: "2027-06-15",
};

const DEMO_CONSTRAINTS: StaffConstraint[] = [
  { id: "1", staffName: "潘建民", constraintType: "no_night", detail: "不可做任何夜更 (N/AN/K10)", effectiveFrom: "2024-01-01" },
  { id: "2", staffName: "李志雄", constraintType: "no_specific_day", detail: "星期日不可做 N 更", effectiveFrom: "2024-01-01" },
];

const DEMO_TOGGLES: ConstraintToggle[] = [
  { id: "s1.1", name: "N 更平均分配", description: "夜更在合資格員工之間平均分配", category: "公平分配", isHard: false },
  { id: "s1.2", name: "# 主管更平均分配", description: "當值主管更期平均分配", category: "公平分配", isHard: false },
  { id: "s1.7", name: "週末工作平均分配", description: "週末工作在員工之間平均分配", category: "公平分配", isHard: false },
  { id: "s3.2", name: "週日廚房補充人手", description: "週日少於2名廚師時，額外派 WA 到廚房", category: "營運效率", isHard: false },
  { id: "s3.3", name: "主管遲食飯", description: "當值主管較遲食飯", category: "營運效率", isHard: false },
];

const DEMO_EVENTS: SpecialEvent[] = [
  { id: "1", name: "外出活動", requiredStaff: "1", requiredRank: "CW", recurring: "weekly_sunday" },
  { id: "2", name: "覆診陪診", requiredStaff: "1", requiredRank: "HW", recurring: "as_needed" },
  { id: "3", name: "PGT 社區老人精神科小組", requiredStaff: "1", requiredRank: "HW (PGT trained)", recurring: "monthly" },
];

const DEMO_PREFS: PersonalPref = {
  preferredShifts: ["A7", "A1030"],
  avoidShifts: ["AN"],
  preferredDaysOff: ["Saturday"],
  notes: "",
};

// ─── Helpers ────────────────────────────────────────────────────────────────
const isAdmin = (role: string) => {
  const r = (role || "").toLowerCase();
  // Include common role names that indicate admin-level access
  return ["owner", "admin", "scheduler", "superintendent", "hp", "nursing", "院長", "主管"].includes(r) || r.includes("admin") || r.includes("super") || r.includes("scheduler");
};

// ─── Main Component ─────────────────────────────────────────────────────────
export default function SettingsPage() {
  const { user } = useAuth();
  // For demo purposes, show admin view if no user or if user has admin-like role
  const userIsAdmin = !user || isAdmin(user?.role || "") || isAdmin(user?.position || "");

  const defaultTab = userIsAdmin ? "facility" : "personal";

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <h1 className="text-lg font-bold text-foreground flex items-center gap-2">
        <Settings size={18} className="text-coral" />
        設定
      </h1>

      <Tabs defaultValue={defaultTab} className="w-full">
        <TabsList className={`w-full grid h-auto p-1 gap-0.5 ${userIsAdmin ? "grid-cols-3" : "grid-cols-1"}`}>
          {userIsAdmin && (
            <>
              <TabsTrigger value="facility" className="text-[11px] py-1.5 px-1">院舍設定</TabsTrigger>
              <TabsTrigger value="constraints" className="text-[11px] py-1.5 px-1">員工限制</TabsTrigger>
              <TabsTrigger value="toggles" className="text-[11px] py-1.5 px-1">排班規則</TabsTrigger>
              <TabsTrigger value="events" className="text-[11px] py-1.5 px-1">特別活動</TabsTrigger>
              <TabsTrigger value="personal" className="text-[11px] py-1.5 px-1">個人偏好</TabsTrigger>
              <TabsTrigger value="imported" className="text-[11px] py-1.5 px-1">外勞管理</TabsTrigger>
            </>
          )}
          {!userIsAdmin && (
            <TabsTrigger value="personal" className="text-[11px] py-1.5 px-1">個人偏好</TabsTrigger>
          )}
        </TabsList>

        {/* ─── Facility Configuration ─────────────────────────────── */}
        {userIsAdmin && (
          <TabsContent value="facility" className="mt-3">
            <FacilityConfigSection />
          </TabsContent>
        )}

        {/* ─── Staff Constraints ──────────────────────────────────── */}
        {userIsAdmin && (
          <TabsContent value="constraints" className="mt-3">
            <StaffConstraintsSection />
          </TabsContent>
        )}

        {/* ─── Constraint Toggles ─────────────────────────────────── */}
        {userIsAdmin && (
          <TabsContent value="toggles" className="mt-3">
            <ConstraintTogglesSection />
          </TabsContent>
        )}

        {/* ─── Special Events ─────────────────────────────────────── */}
        {userIsAdmin && (
          <TabsContent value="events" className="mt-3">
            <SpecialEventsSection />
          </TabsContent>
        )}

        {/* ─── Personal Preferences ───────────────────────────────── */}
        <TabsContent value="personal" className="mt-3">
          <PersonalPrefsSection />
        </TabsContent>

        {/* ─── Imported Staff ─────────────────────────────────────── */}
        {userIsAdmin && (
          <TabsContent value="imported" className="mt-3">
            <ImportedStaffSection />
          </TabsContent>
        )}
      </Tabs>
    </motion.div>
  );
}

// ─── Facility Configuration Section ─────────────────────────────────────────
function FacilityConfigSection() {
  const [config, setConfig] = useState<FacilityConfig>(DEMO_FACILITY);

  const handleSave = () => {
    toast.success("院舍設定已儲存");
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Building2 size={14} className="text-coral" />
          院舍基本設定
        </CardTitle>
        <p className="text-xs text-muted-foreground">設定住客人數、特定鐘點等 SWD 法定要求參數</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Facility Name */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">院舍名稱</Label>
          <Input value={config.facilityName} onChange={(e) => setConfig({ ...config, facilityName: e.target.value })} className="h-10" />
        </div>

        {/* Type & Care Level */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">院舍類型</Label>
            <Select value={config.facilityType} onValueChange={(v) => setConfig({ ...config, facilityType: v })}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="RCHD">殘疾人士院舍 (RCHD)</SelectItem>
                <SelectItem value="RCHE">安老院 (RCHE)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">照顧程度</Label>
            <Select value={config.careLevel} onValueChange={(v) => setConfig({ ...config, careLevel: v })}>
              <SelectTrigger className="h-10"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="high">高度照顧</SelectItem>
                <SelectItem value="medium">中度照顧</SelectItem>
                <SelectItem value="low">低度照顧</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Resident Count */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">每日實際住客數量</Label>
          <Input type="number" value={config.residentCount} onChange={(e) => setConfig({ ...config, residentCount: e.target.value })} className="h-10" />
          <p className="text-[10px] text-muted-foreground">用於計算法定人手比例（如每30住客需1名保健員）</p>
        </div>

        {/* Designated Period */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">指明期間 (Designated Period)</Label>
          <div className="grid grid-cols-2 gap-3">
            <Input type="time" value={config.designatedPeriodStart} onChange={(e) => setConfig({ ...config, designatedPeriodStart: e.target.value })} className="h-10" />
            <Input type="time" value={config.designatedPeriodEnd} onChange={(e) => setConfig({ ...config, designatedPeriodEnd: e.target.value })} className="h-10" />
          </div>
          <p className="text-[10px] text-muted-foreground">SWD 法定日間時段（通常 06:00-22:00）</p>
        </div>

        {/* Specific Hours */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">特定鐘點 (Specific Hours)</Label>
          <div className="grid grid-cols-2 gap-3">
            <Input type="time" value={config.specificHoursStart} onChange={(e) => setConfig({ ...config, specificHoursStart: e.target.value })} className="h-10" />
            <Input type="time" value={config.specificHoursEnd} onChange={(e) => setConfig({ ...config, specificHoursEnd: e.target.value })} className="h-10" />
          </div>
          <p className="text-[10px] text-muted-foreground">社署署長批准的特定鐘點時段，用於計算護士/保健員最低人手</p>
        </div>

        {/* Effective Dates */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">生效日期</Label>
            <Input type="date" value={config.effectiveDate} onChange={(e) => setConfig({ ...config, effectiveDate: e.target.value })} className="h-10" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">終止日期</Label>
            <Input type="date" value={config.expiryDate} onChange={(e) => setConfig({ ...config, expiryDate: e.target.value })} className="h-10" />
          </div>
        </div>

        <Button onClick={handleSave} className="w-full h-10 bg-coral hover:bg-coral-dark text-white font-semibold">
          <Save size={14} className="mr-1.5" />
          儲存設定
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Staff Constraints Section ──────────────────────────────────────────────
function StaffConstraintsSection() {
  const [constraints, setConstraints] = useState<StaffConstraint[]>(DEMO_CONSTRAINTS);
  const [showAdd, setShowAdd] = useState(false);
  const [newStaff, setNewStaff] = useState("");
  const [newType, setNewType] = useState("");
  const [newDetail, setNewDetail] = useState("");

  const handleAdd = () => {
    if (!newStaff || !newType) {
      toast.error("請填寫員工姓名和限制類型");
      return;
    }
    const newConstraint: StaffConstraint = {
      id: Date.now().toString(),
      staffName: newStaff,
      constraintType: newType,
      detail: newDetail,
      effectiveFrom: new Date().toISOString().split("T")[0],
    };
    setConstraints([...constraints, newConstraint]);
    setShowAdd(false);
    setNewStaff("");
    setNewType("");
    setNewDetail("");
    toast.success("已新增員工限制（Hard Constraint）");
  };

  const handleDelete = (id: string) => {
    setConstraints(constraints.filter((c) => c.id !== id));
    toast.success("已刪除限制");
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <UserCog size={14} className="text-coral" />
            員工硬性限制
          </CardTitle>
          <Button size="sm" variant="outline" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs">
            <Plus size={12} className="mr-1" />
            新增
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">新增的限制會即時成為排班引擎的 Hard Constraint</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Add Form */}
        {showAdd && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-3 p-3 bg-muted/50 rounded-xl">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">員工姓名 *</Label>
              <Input value={newStaff} onChange={(e) => setNewStaff(e.target.value)} placeholder="輸入員工姓名" className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">限制類型 *</Label>
              <Select value={newType} onValueChange={setNewType}>
                <SelectTrigger className="h-9"><SelectValue placeholder="選擇類型" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="no_night">不可做夜更</SelectItem>
                  <SelectItem value="no_specific_day">不可做特定日子</SelectItem>
                  <SelectItem value="no_specific_shift">不可做特定更期</SelectItem>
                  <SelectItem value="max_consecutive">最大連續工作日</SelectItem>
                  <SelectItem value="medical">醫療限制</SelectItem>
                  <SelectItem value="custom">自訂限制</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">詳細描述</Label>
              <Input value={newDetail} onChange={(e) => setNewDetail(e.target.value)} placeholder="例：不可做 N/AN/K10 更" className="h-9" />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleAdd} className="flex-1 h-8 bg-coral hover:bg-coral-dark text-white text-xs">確認新增</Button>
              <Button size="sm" variant="outline" onClick={() => setShowAdd(false)} className="h-8 text-xs">取消</Button>
            </div>
          </motion.div>
        )}

        {/* Constraint List */}
        {constraints.map((c) => (
          <div key={c.id} className="flex items-start gap-3 p-3 bg-white rounded-xl border border-border/50">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">{c.staffName}</span>
                <Badge variant="destructive" className="text-[9px] px-1.5 py-0">Hard</Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{c.detail}</p>
              <p className="text-[10px] text-muted-foreground/70 mt-0.5">生效：{c.effectiveFrom}</p>
            </div>
            <Button size="icon" variant="ghost" onClick={() => handleDelete(c.id)} className="h-7 w-7 text-destructive/60 hover:text-destructive">
              <Trash2 size={13} />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ─── Constraint Toggles Section ─────────────────────────────────────────────
function ConstraintTogglesSection() {
  const [toggles, setToggles] = useState<ConstraintToggle[]>(DEMO_TOGGLES);

  const handleToggle = (id: string) => {
    setToggles(toggles.map((t) => t.id === id ? { ...t, isHard: !t.isHard } : t));
    const target = toggles.find((t) => t.id === id);
    if (target) {
      toast.success(target.isHard ? `「${target.name}」改為盡量滿足` : `「${target.name}」改為強制執行`);
    }
  };

  const grouped = toggles.reduce((acc, t) => {
    if (!acc[t.category]) acc[t.category] = [];
    acc[t.category].push(t);
    return acc;
  }, {} as Record<string, ConstraintToggle[]>);

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <ToggleLeft size={14} className="text-coral" />
          排班規則開關
        </CardTitle>
        <p className="text-xs text-muted-foreground">切換「強制執行」= Hard Constraint；「盡量滿足」= Soft Constraint</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {Object.entries(grouped).map(([category, items]) => (
          <div key={category}>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-2">{category}</h3>
            <div className="space-y-2">
              {items.map((t) => (
                <div key={t.id} className="flex items-center justify-between p-3 bg-white rounded-xl border border-border/50">
                  <div className="flex-1 min-w-0 mr-3">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{t.name}</span>
                      <Badge variant={t.isHard ? "destructive" : "secondary"} className="text-[9px] px-1.5 py-0">
                        {t.isHard ? "強制" : "盡量"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">{t.description}</p>
                  </div>
                  <Switch checked={t.isHard} onCheckedChange={() => handleToggle(t.id)} />
                </div>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ─── Special Events Section ─────────────────────────────────────────────────
function SpecialEventsSection() {
  const [events, setEvents] = useState<SpecialEvent[]>(DEMO_EVENTS);
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState("");
  const [newStaff, setNewStaff] = useState("1");
  const [newRank, setNewRank] = useState("");
  const [newRecurring, setNewRecurring] = useState("");

  const handleAdd = () => {
    if (!newName || !newRank) {
      toast.error("請填寫活動名稱和所需職級");
      return;
    }
    setEvents([...events, { id: Date.now().toString(), name: newName, requiredStaff: newStaff, requiredRank: newRank, recurring: newRecurring }]);
    setShowAdd(false);
    setNewName("");
    setNewStaff("1");
    setNewRank("");
    setNewRecurring("");
    toast.success("已新增特別活動（排班引擎會視為 Hard Constraint）");
  };

  const handleDelete = (id: string) => {
    setEvents(events.filter((e) => e.id !== id));
    toast.success("已刪除活動");
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <CalendarHeart size={14} className="text-coral" />
            特別活動類型
          </CardTitle>
          <Button size="sm" variant="outline" onClick={() => setShowAdd(!showAdd)} className="h-7 text-xs">
            <Plus size={12} className="mr-1" />
            新增
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">建立活動後，排班引擎會自動確保有足夠指定職級人手</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {showAdd && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-3 p-3 bg-muted/50 rounded-xl">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">活動名稱 *</Label>
              <Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="例：外出活動" className="h-9" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">所需人數</Label>
                <Input type="number" value={newStaff} onChange={(e) => setNewStaff(e.target.value)} className="h-9" min="1" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs font-medium">所需職級 *</Label>
                <Select value={newRank} onValueChange={setNewRank}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="選擇" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="RN">護士 (RN/EN)</SelectItem>
                    <SelectItem value="HW">保健員 (HW)</SelectItem>
                    <SelectItem value="CW">護理員 (CW)</SelectItem>
                    <SelectItem value="assistant">助理員</SelectItem>
                    <SelectItem value="any">任何員工</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">重複頻率</Label>
              <Select value={newRecurring} onValueChange={setNewRecurring}>
                <SelectTrigger className="h-9"><SelectValue placeholder="選擇" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="once">一次性</SelectItem>
                  <SelectItem value="weekly_sunday">每週日</SelectItem>
                  <SelectItem value="weekly">每週</SelectItem>
                  <SelectItem value="biweekly">每兩週</SelectItem>
                  <SelectItem value="monthly">每月</SelectItem>
                  <SelectItem value="as_needed">按需要</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={handleAdd} className="flex-1 h-8 bg-coral hover:bg-coral-dark text-white text-xs">確認新增</Button>
              <Button size="sm" variant="outline" onClick={() => setShowAdd(false)} className="h-8 text-xs">取消</Button>
            </div>
          </motion.div>
        )}

        {events.map((e) => (
          <div key={e.id} className="flex items-start gap-3 p-3 bg-white rounded-xl border border-border/50">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">{e.name}</span>
                <Badge variant="destructive" className="text-[9px] px-1.5 py-0">Hard</Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                需要 {e.requiredStaff} 名 {e.requiredRank} · {e.recurring === "weekly_sunday" ? "每週日" : e.recurring === "monthly" ? "每月" : e.recurring === "as_needed" ? "按需要" : e.recurring}
              </p>
            </div>
            <Button size="icon" variant="ghost" onClick={() => handleDelete(e.id)} className="h-7 w-7 text-destructive/60 hover:text-destructive">
              <Trash2 size={13} />
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ─── Personal Preferences Section ───────────────────────────────────────────
function PersonalPrefsSection() {
  const [prefs, setPrefs] = useState<PersonalPref>(DEMO_PREFS);
  const [newPrefShift, setNewPrefShift] = useState("");
  const [newAvoidShift, setNewAvoidShift] = useState("");

  const handleSave = () => {
    toast.success("個人偏好已儲存（排班引擎會盡量滿足）");
  };

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold flex items-center gap-2">
          <Heart size={14} className="text-coral" />
          個人排班偏好
        </CardTitle>
        <p className="text-xs text-muted-foreground">你的偏好會作為 Soft Constraint 輸入排班引擎，盡量滿足但不保證</p>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Preferred Shifts */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">偏好更期</Label>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {prefs.preferredShifts.map((s) => (
              <Badge key={s} variant="secondary" className="text-xs cursor-pointer" onClick={() => setPrefs({ ...prefs, preferredShifts: prefs.preferredShifts.filter((x) => x !== s) })}>
                {s} ✕
              </Badge>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={newPrefShift} onChange={(e) => setNewPrefShift(e.target.value)} placeholder="輸入更期代號 (如 A7)" className="h-9 flex-1" />
            <Button size="sm" variant="outline" className="h-9" onClick={() => {
              if (newPrefShift && !prefs.preferredShifts.includes(newPrefShift)) {
                setPrefs({ ...prefs, preferredShifts: [...prefs.preferredShifts, newPrefShift] });
                setNewPrefShift("");
              }
            }}>
              <Plus size={12} />
            </Button>
          </div>
        </div>

        {/* Avoid Shifts */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">盡量避免嘅更期</Label>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {prefs.avoidShifts.map((s) => (
              <Badge key={s} variant="outline" className="text-xs cursor-pointer border-destructive/30 text-destructive" onClick={() => setPrefs({ ...prefs, avoidShifts: prefs.avoidShifts.filter((x) => x !== s) })}>
                {s} ✕
              </Badge>
            ))}
          </div>
          <div className="flex gap-2">
            <Input value={newAvoidShift} onChange={(e) => setNewAvoidShift(e.target.value)} placeholder="輸入更期代號 (如 AN)" className="h-9 flex-1" />
            <Button size="sm" variant="outline" className="h-9" onClick={() => {
              if (newAvoidShift && !prefs.avoidShifts.includes(newAvoidShift)) {
                setPrefs({ ...prefs, avoidShifts: [...prefs.avoidShifts, newAvoidShift] });
                setNewAvoidShift("");
              }
            }}>
              <Plus size={12} />
            </Button>
          </div>
        </div>

        {/* Preferred Days Off */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">偏好休息日</Label>
          <div className="grid grid-cols-4 gap-1.5">
            {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day) => {
              const shortDay = { Monday: "一", Tuesday: "二", Wednesday: "三", Thursday: "四", Friday: "五", Saturday: "六", Sunday: "日" }[day];
              const isSelected = prefs.preferredDaysOff.includes(day);
              return (
                <button
                  key={day}
                  onClick={() => setPrefs({
                    ...prefs,
                    preferredDaysOff: isSelected
                      ? prefs.preferredDaysOff.filter((d) => d !== day)
                      : [...prefs.preferredDaysOff, day],
                  })}
                  className={`py-2 rounded-lg text-xs font-medium transition-all duration-150 active:scale-95 ${
                    isSelected ? "bg-coral text-white" : "bg-muted text-muted-foreground"
                  }`}
                >
                  {shortDay}
                </button>
              );
            })}
          </div>
        </div>

        {/* Notes */}
        <div className="space-y-1.5">
          <Label className="text-xs font-medium">其他備註</Label>
          <Input value={prefs.notes} onChange={(e) => setPrefs({ ...prefs, notes: e.target.value })} placeholder="例：下月有考試，希望減少夜更" className="h-9" />
        </div>

        <Button onClick={handleSave} className="w-full h-10 bg-coral hover:bg-coral-dark text-white font-semibold">
          <Save size={14} className="mr-1.5" />
          儲存偏好
        </Button>
      </CardContent>
    </Card>
  );
}

// ─── Imported Staff Section ─────────────────────────────────────────────────
function ImportedStaffSection() {
  const [importedStaff] = useState([
    { id: "1", name: "Maria Santos", shiftDuration: "12h", restBetween: "12h", monthlyDO: 4, status: "active" },
    { id: "2", name: "Nguyen Thi Lan", shiftDuration: "12h", restBetween: "12h", monthlyDO: 4, status: "active" },
  ]);

  return (
    <Card className="border-0 shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Users size={14} className="text-coral" />
            外勞管理
          </CardTitle>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => toast("功能開發中", { description: "將可從員工列表標記外勞身份" })}>
            <Plus size={12} className="mr-1" />
            標記外勞
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">標記為外勞的員工會自動套用：每更12小時、更間休息12小時、每月4日假</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {importedStaff.map((s) => (
          <div key={s.id} className="p-3 bg-white rounded-xl border border-border/50">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">{s.name}</span>
              <Badge variant="secondary" className="text-[9px]">外勞</Badge>
            </div>
            <div className="flex gap-3 mt-2">
              <span className="text-[10px] text-muted-foreground">每更 {s.shiftDuration}</span>
              <span className="text-[10px] text-muted-foreground">休息 ≥{s.restBetween}</span>
              <span className="text-[10px] text-muted-foreground">{s.monthlyDO} DO/月</span>
            </div>
          </div>
        ))}

        <div className="p-3 bg-pink-50/80 rounded-xl">
          <p className="text-xs text-pink-800 font-medium">⚠️ 外勞規則為 Hard Constraint</p>
          <p className="text-[10px] text-pink-700 mt-0.5">排班引擎絕對不會違反以上規則。如有特殊情況需要調整，請聯絡系統管理員。</p>
        </div>
      </CardContent>
    </Card>
  );
}
