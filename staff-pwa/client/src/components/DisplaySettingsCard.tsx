import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useTheme, type TextSize } from "@/contexts/ThemeContext";

const SIZE_OPTIONS: { value: TextSize; label: string; pixels: string }[] = [
  { value: "standard", label: "A・精簡", pixels: "16 px" },
  { value: "comfortable", label: "AA・預設", pixels: "18 px" },
  { value: "large", label: "AAA・大字", pixels: "22 px" },
];

export function DisplaySettingsCard() {
  const { theme, setTheme, textSize, setTextSize } = useTheme();
  return <Card className="border border-border bg-card text-card-foreground shadow-sm">
    <CardHeader className="pb-2"><CardTitle className="text-sm">顯示設定</CardTitle></CardHeader>
    <CardContent className="space-y-3">
      <p className="text-xs text-muted-foreground">可配合瀏覽器放大；選擇只儲存在這部裝置上的當前帳戶，不會同步院舍資料庫。</p>
      <div role="group" aria-label="文字大小" className="grid grid-cols-3 gap-1.5">
        {SIZE_OPTIONS.map(option => <button key={option.value} type="button" aria-pressed={textSize === option.value} onClick={() => setTextSize(option.value)}
          className={`min-h-12 rounded-lg border p-1 text-xs font-semibold ${textSize === option.value ? "border-coral bg-coral/10 text-foreground" : "border-border bg-background text-foreground"}`}>
          {option.label}<span className="block text-xs font-normal">{option.pixels}</span>
        </button>)}
      </div>
      <label className="flex min-h-11 items-center justify-between gap-2 text-sm">
        <span>深色模式（測試預覽）</span>
        <input type="checkbox" role="switch" aria-label="深色模式" checked={theme === "dark"} onChange={e => setTheme(e.target.checked ? "dark" : "light")}
          className="h-5 w-5 accent-[#E8187A]" />
      </label>
      <p className="text-xs text-muted-foreground">部分舊畫面仍使用固定顏色，推出前須逐頁核對對比度與放大後版面。</p>
    </CardContent>
  </Card>;
}
