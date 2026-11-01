import React, { createContext, useContext, useEffect, useState } from "react";
import { useAuth } from "./AuthContext";

export type Theme = "light" | "dark";
export type TextSize = "standard" | "comfortable" | "large";
interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  textSize: TextSize;
  setTextSize: (size: TextSize) => void;
}
const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
const DEFAULT: { theme: Theme; textSize: TextSize } = { theme: "light", textSize: "comfortable" };

export function ThemeProvider({ children }: { children: React.ReactNode; defaultTheme?: Theme; switchable?: boolean }) {
  const { user } = useAuth();
  const id = user?.id || null;
  const [prefs, setPrefs] = useState(DEFAULT);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  useEffect(() => {
    let next = DEFAULT;
    if (id) {
      try {
        const saved = JSON.parse(localStorage.getItem(`emma_pwa_display_v1:${id}`) || "{}") as Partial<typeof DEFAULT>;
        next = {
          theme: saved.theme === "dark" ? "dark" : "light",
          textSize: ["standard", "comfortable", "large"].includes(saved.textSize || "") ? saved.textSize! : "comfortable",
        };
      } catch { next = DEFAULT; }
    }
    setPrefs(next);
    setLoadedFor(id);
  }, [id]);

  useEffect(() => {
    if (id && loadedFor !== id) return;
    const root = document.documentElement;
    root.classList.toggle("dark", prefs.theme === "dark");
    root.dataset.emmaTextSize = prefs.textSize;
    root.style.fontSize = ({ standard: "16px", comfortable: "18px", large: "22px" })[prefs.textSize];
    if (id) localStorage.setItem(`emma_pwa_display_v1:${id}`, JSON.stringify(prefs));
  }, [id, loadedFor, prefs]);

  const value: ThemeContextType = {
    ...prefs,
    setTheme: theme => setPrefs(p => ({ ...p, theme })),
    toggleTheme: () => setPrefs(p => ({ ...p, theme: p.theme === "dark" ? "light" : "dark" })),
    setTextSize: textSize => setPrefs(p => ({ ...p, textSize })),
  };
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used within ThemeProvider");
  return value;
}
