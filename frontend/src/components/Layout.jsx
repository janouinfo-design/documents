import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Truck,
  CalendarClock,
  Menu,
  X,
  Layers3,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Sheet, SheetContent } from "@/components/ui/sheet";

const NAV = [
  { to: "/", label: "Tableau de bord", icon: LayoutDashboard, testId: "nav-dashboard" },
  { to: "/vehicules", label: "Véhicules", icon: Truck, testId: "nav-vehicles" },
  { to: "/timeline", label: "Échéances", icon: CalendarClock, testId: "nav-timeline" },
];

function NavItems({ onNavigate }) {
  const { pathname } = useLocation();
  const renderGroup = (items, label) => (
    <div className="space-y-1">
      {label && (
        <p className="px-3 pb-2 pt-5 text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
          {label}
        </p>
      )}
      {items.map(({ to, label, icon: Icon, testId }) => {
        const active = pathname === to;
        return (
          <Link
            key={to}
            to={to}
            onClick={onNavigate}
            data-testid={testId}
            className={cn(
              "group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-200",
              active
                ? "bg-slate-900 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            )}
          >
            <Icon className={cn("h-[18px] w-[18px] shrink-0", active ? "text-white" : "text-slate-400 group-hover:text-slate-700")} />
            {label}
          </Link>
        );
      })}
    </div>
  );

  return (
    <nav className="flex flex-col gap-1 px-3">
      {renderGroup(NAV, "Administration")}
    </nav>
  );
}

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-5 py-6" data-testid="brand-logo">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white">
        <Layers3 className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <p className="font-display text-lg font-extrabold tracking-tight text-slate-900">LogiTrak</p>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Fleet Admin</p>
      </div>
    </Link>
  );
}

export default function Layout({ children }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto pb-6">
          <NavItems />
        </div>
        <div className="border-t border-slate-200 px-5 py-4">
          <p className="text-xs text-slate-400">Gestion administrative</p>
          <p className="text-xs font-semibold text-slate-600">de flotte · 2026</p>
        </div>
      </aside>

      {/* Mobile drawer */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 p-0">
          <Brand />
          <NavItems onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      {/* Main */}
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/80 px-4 backdrop-blur-md sm:px-6 lg:px-8">
          <button
            onClick={() => setMobileOpen(true)}
            data-testid="mobile-menu-btn"
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-600 lg:hidden"
            aria-label="Ouvrir le menu"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="flex flex-col">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
              Module
            </p>
            <h1 className="font-display text-base font-bold leading-none tracking-tight text-slate-900">
              Gestion administrative de flotte
            </h1>
          </div>
        </header>
        <main className="mx-auto max-w-[1400px] p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
