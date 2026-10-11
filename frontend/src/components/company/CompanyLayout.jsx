import { NavLink, Outlet } from "react-router-dom";
import { Wallet, Users, HandCoins, CalendarCheck } from "lucide-react";

const links = [
  ["/company", "Kasa", Wallet, "company-overview"],
  ["/company/capital", "Sermaye & Hisseler", Users, "company-capital"],
  ["/company/debts", "Borç & Alacak", HandCoins, "company-debts"],
  ["/company/closings", "Aylık Kapanışlar", CalendarCheck, "company-closings"],
];
export const CompanyLayout = () => <div className="space-y-6" data-testid="company-layout">
  <header><p className="text-xs uppercase font-semibold text-emerald-700 mb-2" data-testid="company-scope">Şirket geneli · Tüm mağazalar</p><h1 className="font-display text-3xl sm:text-4xl font-extrabold">Sermaye & Kasa</h1></header>
  <nav className="flex flex-wrap gap-2 border-b border-slate-200 pb-4" aria-label="Şirket finansı">
    {links.map(([to, label, Icon, id]) => <NavLink key={to} end={to === "/company"} to={to} data-testid={`nav-${id}`} className={({ isActive }) => `inline-flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors ${isActive ? "bg-emerald-700 text-white" : "text-slate-600 hover:bg-white"}`}><Icon className="w-4 h-4" />{label}</NavLink>)}
  </nav><Outlet />
</div>;