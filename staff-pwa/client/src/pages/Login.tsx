import { useState } from "react";
import { useLocation } from "wouter";
import { isConfiguredApiOrigin, login } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Loader2 } from "lucide-react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setUser } = useAuth();
  const [, setLocation] = useLocation();
  const backendConfigured = isConfiguredApiOrigin();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!backendConfigured) return;
    setError("");
    setLoading(true);
    try {
      const data = await login(email, password);
      setUser(data.user);
      setLocation("/");
    } catch (err: any) {
      setError(err.message || "登入失敗");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_50%_24%,rgba(232,24,122,0.12),transparent_34%),linear-gradient(180deg,#fff5f9_0%,#ffffff_100%)] flex flex-col items-center justify-center px-6">
      <div className="mb-7 text-center">
        <img
          src="/icons/emma-logo-192.png"
          alt=""
          className="w-[72px] h-[72px] mx-auto mb-3"
        />
        <h1 className="text-[28px] leading-none font-extrabold tracking-[-0.035em] text-foreground">Emma AI</h1>
        <p className="text-sm font-medium text-coral-dark mt-2">你嘅院舍工作拍檔</p>
        <p className="text-xs text-muted-foreground mt-1">安心睇更 · 清楚處理申請</p>
      </div>

      <Card className="w-full max-w-sm border border-white/90 bg-white/92 shadow-[0_22px_55px_rgba(79,38,38,0.10),inset_0_1px_0_rgba(255,255,255,0.95)] ring-1 ring-coral/5 rounded-[26px]">
        <CardContent className="pt-7 pb-6 px-6">
          <div className="mb-5">
            <h2 className="text-lg font-bold tracking-tight text-foreground">歡迎返嚟</h2>
            <p className="text-xs text-muted-foreground mt-1">登入查看你嘅更表、工作同最新通知。</p>
          </div>
          {!backendConfigured && (
            <p role="status" className="mb-5 rounded-xl border border-pink-200 bg-pink-50 p-3 text-sm text-slate-700">
              整合預覽：登入暫停，待後端權限及資料隔離驗收後啟用。請勿輸入正式密碼。
              <span lang="en" className="mt-2 block">Integration preview: sign-in is disabled pending backend permission and data-isolation acceptance.</span>
            </p>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-sm font-semibold text-slate-700">電郵地址</Label>
              <Input
                id="email"
                type="email"
                placeholder="your.name@emma.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                disabled={!backendConfigured || loading}
                className="h-12 rounded-xl border-slate-200 bg-[#fffcfa] focus-visible:ring-coral/35"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-sm font-semibold text-slate-700">密碼</Label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={!backendConfigured || loading}
                className="h-12 rounded-xl border-slate-200 bg-[#fffcfa] focus-visible:ring-coral/35"
              />
            </div>
            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2">
                {error}
              </p>
            )}
            <Button
              type="submit"
              className="w-full h-12 rounded-xl bg-[#E8187A] hover:bg-[#b81360] text-white font-bold shadow-[0_10px_24px_rgba(232,24,122,0.16)]"
              disabled={loading || !backendConfigured}
            >
              {loading ? <Loader2 className="animate-spin mr-2" size={18} /> : null}
              登入
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
