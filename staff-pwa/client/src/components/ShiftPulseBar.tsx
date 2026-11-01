/** Clinical Warmth: compact live shift status with honest empty states. */
import { useEffect, useState } from "react";
import { Clock } from "lucide-react";
import { getMyRoster, type RosterDay } from "@/lib/api";

const SHIFT_COLORS: Record<string, string> = {
  A: "from-[#fdb4c9] to-[#E8187A]",
  P: "from-[#f9a8c9] to-[#E8187A]",
  N: "from-[#6366F1] to-[#4338CA]",
  DO: "from-[#86EFAC] to-[#22C55E]",
  AL: "from-[#86EFAC] to-[#22C55E]",
  SL: "from-[#D1D5DB] to-[#9CA3AF]",
  CL: "from-[#D1D5DB] to-[#9CA3AF]",
  NONE: "from-[#334155] to-[#172033]",
};

const SHIFT_LABELS: Record<string, string> = {
  A: "早更", P: "午更", N: "夜更", DO: "休息", AL: "年假", SL: "病假", CL: "補假",
};

const isoDate = (date = new Date()) => date.toISOString().slice(0, 10);
const hhmm = (value?: string | null) => value?.slice(0, 5) || "";

export function ShiftPulseBar() {
  const [shift, setShift] = useState<RosterDay | null>(null);
  const [countdown, setCountdown] = useState("載入更表中");

  useEffect(() => {
    const today = isoDate();
    getMyRoster(today, today)
      .then((data) => setShift(data.days[0] || null))
      .catch(() => setShift(null));
  }, []);

  useEffect(() => {
    const updateCountdown = () => {
      if (!shift?.is_working || !shift.start_time || !shift.end_time) {
        setCountdown("今日未有已發佈更期");
        return;
      }
      const now = new Date();
      const [sh, sm] = shift.start_time.split(":").map(Number);
      const [eh, em] = shift.end_time.split(":").map(Number);
      const start = new Date(now);
      const end = new Date(now);
      start.setHours(sh, sm, 0, 0);
      end.setHours(eh, em, 0, 0);
      if (end <= start) end.setDate(end.getDate() + 1);
      const target = now < start ? start : end;
      const diff = Math.max(0, target.getTime() - now.getTime());
      const hours = Math.floor(diff / 3_600_000);
      const mins = Math.floor((diff % 3_600_000) / 60_000);
      setCountdown(now < start ? `${hours}h ${mins}m 後開始` : diff ? `尚餘 ${hours}h ${mins}m` : "更期已結束");
    };
    updateCountdown();
    const timer = window.setInterval(updateCountdown, 60_000);
    return () => window.clearInterval(timer);
  }, [shift]);

  const type = shift?.shift_type || "NONE";
  return (
    <div className={`bg-gradient-to-r ${SHIFT_COLORS[type] || SHIFT_COLORS.NONE} px-4 py-3 flex items-center justify-between sticky top-0 z-40 text-white`}>
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-mono font-semibold text-sm">{shift?.shift_type || "—"}</span>
        <span className="text-sm font-medium">{SHIFT_LABELS[type] || (shift?.is_working ? "當值" : "未排班")}</span>
        {shift?.is_working && <span className="text-xs opacity-80">{hhmm(shift.start_time)}–{hhmm(shift.end_time)}</span>}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <Clock size={14} className="opacity-80" />
        <span className="font-mono text-[10px] font-medium">{countdown}</span>
      </div>
    </div>
  );
}
