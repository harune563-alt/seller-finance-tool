import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useStore } from "@/contexts/StoreContext";
import { MARKETPLACES, MP_BY_CODE } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  LayoutDashboard, Receipt, Wallet, FileBarChart2, Store as StoreIcon,
  LogOut, ChevronDown, Globe,
} from "lucide-react";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, testId: "nav-dashboard" },
  { to: "/transactions", label: "Gelir / Gider", icon: Receipt, testId: "nav-transactions" },
  { to: "/payouts", label: "Amazon Ödemeleri", icon: Wallet, testId: "nav-payouts" },
  { to: "/report", label: "Kar-Zarar Raporu", icon: FileBarChart2, testId: "nav-report" },
  { to: "/stores", label: "Mağazalar", icon: StoreIcon, testId: "nav-stores" },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const {
    stores, activeStore, activeStoreId, setActiveStoreId,
    activeMarketplace, setActiveMarketplace,
  } = useStore();

  const availableMps = activeStore
    ? ["ALL", ...(activeStore.marketplaces || [])]
    : ["ALL"];

  const onLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top bar */}
      <header className="h-16 border-b border-slate-200 bg-white sticky top-0 z-40">
        <div className="max-w-[1600px] mx-auto h-full px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
          <Link to="/" className="flex items-center gap-2" data-testid="brand-logo">
            <div className="w-9 h-9 rounded-xl bg-slate-900 flex items-center justify-center">
              <span className="text-amber-400 font-display text-xl font-extrabold leading-none">a</span>
            </div>
            <div className="hidden sm:block">
              <div className="font-display font-extrabold text-slate-900 text-base leading-none">Seller Suite</div>
              <div className="text-[11px] text-slate-500 tracking-wide">Kar/Zarar · Bakiye Takip</div>
            </div>
          </Link>

          <div className="flex items-center gap-2">
            {/* Store Switcher */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="gap-2 bg-white" data-testid="store-switcher-dropdown">
                  <StoreIcon className="w-4 h-4 text-slate-500" />
                  <span className="truncate max-w-[140px]">
                    {activeStore ? activeStore.name : "Mağaza seçin"}
                  </span>
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-white w-56">
                <DropdownMenuLabel>Mağazalarım</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {stores.length === 0 && (
                  <DropdownMenuItem disabled>Henüz mağaza yok</DropdownMenuItem>
                )}
                {stores.map((s) => (
                  <DropdownMenuItem
                    key={s.id}
                    onSelect={() => setActiveStoreId(s.id)}
                    data-testid={`store-option-${s.id}`}
                    className={activeStoreId === s.id ? "bg-slate-100 font-semibold" : ""}
                  >
                    <StoreIcon className="w-4 h-4 mr-2 text-slate-500" /> {s.name}
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => navigate("/stores")} data-testid="manage-stores-btn">
                  Mağazaları Yönet
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Marketplace Switcher */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="gap-2 bg-white" data-testid="marketplace-switcher">
                  <Globe className="w-4 h-4 text-slate-500" />
                  <span>
                    {activeMarketplace === "ALL"
                      ? "🌐 Tüm Pazarlar"
                      : `${MP_BY_CODE[activeMarketplace]?.flag || ""} ${activeMarketplace}`}
                  </span>
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-white w-56 max-h-[380px] overflow-y-auto">
                <DropdownMenuLabel>Pazar Yeri</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {availableMps.map((code) => {
                  if (code === "ALL") {
                    return (
                      <DropdownMenuItem
                        key="ALL"
                        onSelect={() => setActiveMarketplace("ALL")}
                        data-testid="mp-option-ALL"
                      >
                        🌐 Tüm Pazarlar
                      </DropdownMenuItem>
                    );
                  }
                  const m = MP_BY_CODE[code];
                  return (
                    <DropdownMenuItem
                      key={code}
                      onSelect={() => setActiveMarketplace(code)}
                      data-testid={`mp-option-${code}`}
                    >
                      <span className="mr-2">{m?.flag}</span>
                      <span className="flex-1">{m?.name}</span>
                      <span className="text-xs text-slate-400 ml-2">{m?.currency}</span>
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="gap-2" data-testid="user-menu-btn">
                  <div className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center text-sm font-semibold">
                    {(user?.name || user?.email || "?")[0].toUpperCase()}
                  </div>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="bg-white w-52">
                <DropdownMenuLabel>
                  <div className="font-semibold truncate">{user?.name}</div>
                  <div className="text-xs text-slate-500 truncate">{user?.email}</div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={onLogout} data-testid="logout-btn" className="text-rose-600">
                  <LogOut className="w-4 h-4 mr-2" /> Çıkış Yap
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      {/* Secondary Nav */}
      <nav className="bg-slate-900 border-b border-slate-800">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 flex items-center gap-1 overflow-x-auto">
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                data-testid={item.testId}
                className={({ isActive }) =>
                  `flex items-center gap-2 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                    isActive
                      ? "text-amber-400 border-amber-400"
                      : "text-slate-300 border-transparent hover:text-white hover:border-slate-500"
                  }`
                }
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </NavLink>
            );
          })}
        </div>
      </nav>

      {/* Content */}
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Outlet />
      </main>
    </div>
  );
}
