import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function Login() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("admin@amzsuite.com");
  const [password, setPassword] = useState("admin123");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await login(email, password);
      toast.success("Hoş geldin!");
      navigate("/");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Giriş başarısız");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-grid bg-slate-50">
      <div className="hidden lg:flex flex-1 relative bg-slate-900 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-900/40" />
        <div className="relative z-10 p-14 flex flex-col justify-between text-white">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-amber-400 flex items-center justify-center">
              <span className="text-slate-900 font-display font-extrabold text-2xl">a</span>
            </div>
            <div>
              <div className="font-display text-xl font-extrabold">Amazon Seller Suite</div>
              <div className="text-xs text-slate-400">Çok Pazarlı Kar/Zarar Takibi</div>
            </div>
          </div>
          <div className="space-y-6 max-w-md">
            <h1 className="font-display text-4xl font-extrabold leading-tight">
              Tüm pazarlardaki<br/>
              <span className="text-amber-400">kar ve bakiyeni</span><br/>
              tek panelden yönet.
            </h1>
            <p className="text-slate-300 text-sm leading-relaxed">
              US, Kanada, Meksika, UK, Almanya, Avustralya ve daha fazlası —
              her mağaza için ayrı gelir, gider ve Amazon ödeme kayıtları.
            </p>
            <div className="grid grid-cols-3 gap-3 pt-4">
              {["🇺🇸","🇨🇦","🇲🇽","🇬🇧","🇩🇪","🇦🇺"].map((f, i) => (
                <div key={i} className="h-14 rounded-xl bg-white/5 border border-white/10 flex items-center justify-center text-2xl">
                  {f}
                </div>
              ))}
            </div>
          </div>
          <div className="text-xs text-slate-400">© 2026 Seller Suite</div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-md bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
          <h2 className="font-display text-2xl font-extrabold text-slate-900">Giriş Yap</h2>
          <p className="text-sm text-slate-500 mt-1">Hesabına giriş yaparak panele devam et.</p>

          <div className="mt-6 space-y-4">
            <div>
              <Label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-slate-600">E-posta</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                     required data-testid="login-email-input" className="mt-1" />
            </div>
            <div>
              <Label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-slate-600">Şifre</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                     required data-testid="login-password-input" className="mt-1" />
            </div>
            <Button type="submit" disabled={loading} data-testid="login-submit-button"
                    className="w-full bg-slate-900 hover:bg-slate-800 text-white h-11 rounded-xl font-semibold">
              {loading ? "Giriş yapılıyor..." : "Giriş Yap"}
            </Button>
          </div>

          <div className="mt-4 text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div className="font-semibold text-slate-700 mb-1">Demo hesap:</div>
            admin@amzsuite.com / admin123
          </div>

          <p className="mt-6 text-sm text-slate-600 text-center">
            Hesabın yok mu?{" "}
            <Link to="/register" className="text-emerald-600 hover:underline font-semibold" data-testid="go-register-link">
              Kayıt ol
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
