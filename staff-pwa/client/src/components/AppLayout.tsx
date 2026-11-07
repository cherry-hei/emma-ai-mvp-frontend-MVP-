/** Clinical Warmth: persistent navigation with live operational attention count. */
/**
 * Clinical Warmth navigation: the coral badge is driven by one shared, calm
 * live-attention source rather than page-level duplicate requests.
 */
import { type ReactNode } from "react";
import { useLocation } from "wouter";
import { Home, ClipboardList, Calendar, FileBarChart, MessageCircle } from "lucide-react";
import { motion } from "framer-motion";
import { useAttention } from "@/contexts/AttentionContext";
import { ShiftPulseBar } from "./ShiftPulseBar";

const tabs = [
  { path: "/", icon: Home, label: "首頁" },
  { path: "/tasks", icon: ClipboardList, label: "工作" },
  { path: "/roster", icon: Calendar, label: "更表" },
  { path: "/records", icon: FileBarChart, label: "紀錄" },
  { path: "/messages", icon: MessageCircle, label: "通知" },
];

export function AppLayout({ children }: { children: ReactNode }) {
  const [location, setLocation] = useLocation();
  const { attentionCount } = useAttention();

  return (
    <div className="min-h-screen bg-background flex flex-col max-w-md mx-auto relative">
      <ShiftPulseBar />
      <main className="flex-1 overflow-y-auto pb-20 px-4 pt-3">{children}</main>
      <nav className="fixed bottom-0 left-0 right-0 max-w-md mx-auto bg-card/95 text-card-foreground backdrop-blur-xl border-t border-border z-50">
        <div className="flex items-center justify-around py-2 px-2">
          {tabs.map((tab) => {
            const isActive = location === tab.path || (tab.path !== "/" && location.startsWith(tab.path));
            const Icon = tab.icon;
            return (
              <button key={tab.path} onClick={() => setLocation(tab.path)} className="flex flex-col items-center gap-0.5 py-1 px-3 rounded-xl transition-all duration-150 relative">
                {isActive && <motion.div layoutId="tab-indicator" className="absolute inset-0 bg-coral/10 rounded-xl" transition={{ type: "spring", stiffness: 500, damping: 35 }} />}
                <div className="relative">
                  <Icon size={22} className={`relative z-10 transition-colors duration-150 ${isActive ? "text-coral" : "text-muted-foreground"}`} />
                  {tab.path === "/messages" && attentionCount > 0 && (
                    <span className="absolute -top-1.5 -right-2 min-w-[18px] h-5 px-1 rounded-full bg-coral text-white text-xs font-bold flex items-center justify-center z-20">
                      {attentionCount > 99 ? "99+" : attentionCount}
                    </span>
                  )}
                </div>
                <span className={`text-xs font-medium relative z-10 ${isActive ? "text-coral" : "text-muted-foreground"}`}>{tab.label}</span>
              </button>
            );
          })}
        </div>
        <div className="h-[env(safe-area-inset-bottom)]" />
      </nav>
    </div>
  );
}
