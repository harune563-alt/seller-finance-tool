import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function Register() {
  const navigate = useNavigate();
  const { register } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(email, password, name);
      toast.success("Hesabın oluşturuldu!");
      navigate("/");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Kayıt başarısız");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 bg-grid p-6">
      <form onSubmit={submit} className="w-full max-w-md bg-white rounded-2xl border border-slate-200 p-8 shadow-sm">
        <h2 className="font-display text-2xl font-extrabold text-slate-900">Kayıt Ol</h2>
        <p className="text-sm text-slate-500 mt-1">Yeni hesap oluştur ve pazarlarını takibe al.</p>

        <div className="mt-6 space-y-4">
          <div>
            <Label htmlFor="name" className="text-xs font-semibold uppercase tracking-wider text-slate-600">Ad Soyad</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)}
                   data-testid="register-name-input" className="mt-1" />
          </div>
          <div>
            <Label htmlFor="email" className="text-xs font-semibold uppercase tracking-wider text-slate-600">E-posta</Label>
            <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                   required data-testid="register-email-input" className="mt-1" />
          </div>
          <div>
            <Label htmlFor="password" className="text-xs font-semibold uppercase tracking-wider text-slate-600">Şifre</Label>
            <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   required minLength={4} data-testid="register-password-input" className="mt-1" />
          </div>
          <Button type="submit" disabled={loading} data-testid="register-submit-button"
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white h-11 rounded-xl font-semibold">
            {loading ? "Oluşturuluyor..." : "Hesap Oluştur"}
          </Button>
        </div>

        <p className="mt-6 text-sm text-slate-600 text-center">
          Hesabın var mı?{" "}
          <Link to="/login" className="text-emerald-600 hover:underline font-semibold" data-testid="go-login-link">
            Giriş yap
          </Link>
        </p>
      </form>
    </div>
  );
}
