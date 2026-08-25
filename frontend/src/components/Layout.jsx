import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard, Truck, CalendarClock, Bell, Layers3, UserCircle2, KeyRound, LogOut, ShieldCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import ChangePasswordDialog from "@/components/ChangePasswordDialog";

const NAV = [
  { to: "/", label: "Tableau de bord", icon: LayoutDashboard, testId: "nav-dashboard" },
  { to: "/vehicules", label: "Véhicules", icon: Truck, testId: "nav-vehicles" },
  { to: "/timeline", label: "Échéances", icon: CalendarClock, testId: "nav-timeline" },
  { to: "/alertes", label: "Alertes", icon: Bell, testId: "nav-alerts" },
  { to: "/integrite", label: "Intégrité", icon: ShieldCheck, testId: "nav-integrity" },
];

function Brand() {
  return (
    <Link to="/" className="flex shrink-0 items-center gap-2.5" data-testid="brand-logo">
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

function TopTabs() {
  const { pathname } = useLocation();
  return (
    <nav className="no-scrollbar -mb-px flex items-center gap-1 overflow-x-auto" data-testid="top-nav">
      {NAV.map(({ to, label, icon: Icon, testId }) => {
        const active = pathname === to;
        return (
          <Link
            key={to}
            to={to}
            data-testid={testId}
            className={cn(
              "group flex shrink-0 items-center gap-2 border-b-2 px-3.5 py-3 text-sm font-medium transition-colors duration-200",
              active
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-900"
            )}
          >
            <Icon
              className={cn(
                "h-[18px] w-[18px] shrink-0 transition-colors",
                active ? "text-slate-900" : "text-slate-400 group-hover:text-slate-600"
              )}
            />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const [pwdOpen, setPwdOpen] = useState(false);
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            data-testid="user-menu-btn"
            aria-label="Compte"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
          >
            <UserCircle2 className="h-6 w-6" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel data-testid="user-menu-email" className="truncate text-xs font-normal text-slate-500">
            {user?.email}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem data-testid="user-menu-change-password" onSelect={() => setPwdOpen(true)}>
            <KeyRound className="mr-2 h-4 w-4 text-slate-400" /> Changer le mot de passe
          </DropdownMenuItem>
          <DropdownMenuItem data-testid="user-menu-logout" onSelect={logout} className="text-red-600 focus:text-red-600">
            <LogOut className="mr-2 h-4 w-4" /> Se déconnecter
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ChangePasswordDialog open={pwdOpen} onOpenChange={setPwdOpen} />
    </>
  );
}

export default function Layout({ children }) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Brand />
          <div className="flex items-center gap-4">
            <div className="hidden flex-col text-right sm:flex">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Module</p>
              <p className="font-display text-sm font-bold leading-none tracking-tight text-slate-900">
                Gestion administrative de flotte
              </p>
            </div>
            <UserMenu />
          </div>
        </div>
        <div className="border-t border-slate-100">
          <div className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8">
            <TopTabs />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1400px] p-4 sm:p-6 lg:p-8">{children}</main>
    </div>
  );
}
