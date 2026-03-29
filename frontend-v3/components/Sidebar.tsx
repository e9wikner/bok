"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  Receipt,
  BarChart3,
  Brain,
  Settings,
  ChevronLeft,
  ChevronRight,
  Moon,
  Sun,
  Shield,
  AlertTriangle,
  Building2,
  LogOut,
} from "lucide-react";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useAuth } from "@/hooks/useAuth";
import { useState, useRef, useEffect } from "react";
import TenantSelector from "@/components/TenantSelector";
import TenantSelectorCompact from "@/components/TenantSelectorCompact";

const navItems = [
  { href: "/", label: "Översikt", icon: LayoutDashboard },
  { href: "/vouchers", label: "Verifikationer", icon: FileText },
  { href: "/accounts", label: "Kontoplan", icon: BookOpen },
  { href: "/invoices", label: "Fakturor", icon: Receipt },
  { href: "/reports", label: "Rapporter", icon: BarChart3 },
  { href: "/anomalies", label: "Anomalier", icon: AlertTriangle },
  { href: "/learning", label: "AI-lärande", icon: Brain },
  { href: "/settings", label: "Inställningar", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { isDark, toggle } = useDarkMode();
  const { logout, user } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Mobile top-bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-card border-b px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <Shield className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="font-bold text-lg">AIBok</span>
        </div>
        {/* TenantSelector visible in mobile top-bar */}
        <div className="flex items-center gap-2">
          <TenantSelectorCompact />
          <button onClick={toggle} className="p-2 rounded-lg hover:bg-accent">
            {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 bg-card border-t">
        <div className="flex items-center justify-around py-2">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded-lg text-[10px] transition-colors min-w-0",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <item.icon className="h-5 w-5" />
                <span className="truncate max-w-[56px]">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden lg:flex flex-col h-screen sticky top-0 border-r bg-card transition-all duration-300",
          collapsed ? "w-[72px]" : "w-[260px]"
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 h-16 border-b">
          <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
            <Shield className="h-5 w-5 text-primary-foreground" />
          </div>
          {!collapsed && (
            <div className="overflow-hidden">
              <h1 className="font-bold text-lg leading-tight">AIBok</h1>
              <p className="text-xs text-muted-foreground">Bokföringssystem</p>
            </div>
          )}
        </div>

        {/* Tenant selector */}
        {collapsed ? <TenantSelectorCollapsed /> : <TenantSelector />}

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto scrollbar-thin">
          {navItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                  collapsed && "justify-center px-0"
                )}
                title={collapsed ? item.label : undefined}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* Bottom actions */}
        <div className="border-t p-3 space-y-1">
          <button
            onClick={toggle}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all w-full",
              collapsed && "justify-center px-0"
            )}
            title={isDark ? "Ljust läge" : "Mörkt läge"}
          >
            {isDark ? (
              <Sun className="h-5 w-5 flex-shrink-0" />
            ) : (
              <Moon className="h-5 w-5 flex-shrink-0" />
            )}
            {!collapsed && <span>{isDark ? "Ljust läge" : "Mörkt läge"}</span>}
          </button>

          {user && (
            <button
              onClick={logout}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all w-full",
                collapsed && "justify-center px-0"
              )}
              title="Logga ut"
            >
              <LogOut className="h-5 w-5 flex-shrink-0" />
              {!collapsed && <span>Logga ut</span>}
            </button>
          )}

          <button
            onClick={() => setCollapsed((v) => !v)}
            className={cn(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-all w-full",
              collapsed && "justify-center px-0"
            )}
          >
            {collapsed ? (
              <ChevronRight className="h-5 w-5 flex-shrink-0" />
            ) : (
              <ChevronLeft className="h-5 w-5 flex-shrink-0" />
            )}
            {!collapsed && <span>Minimera</span>}
          </button>
        </div>
      </aside>
    </>
  );
}

/** Collapsed desktop sidebar: show Building2 icon that opens a popover */
function TenantSelectorCollapsed() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  return (
    <div ref={ref} className="relative flex justify-center py-3 border-b border-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="p-2 rounded-lg hover:bg-accent text-muted-foreground hover:text-accent-foreground transition-colors"
        title="Välj företag"
      >
        <Building2 className="h-5 w-5" />
      </button>

      {open && (
        <div className="absolute left-full top-0 ml-2 z-50 w-64 rounded-lg border border-border bg-card shadow-lg">
          <div className="px-3 py-2 border-b">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Välj företag
            </p>
          </div>
          <div className="p-1">
            <TenantSelector />
          </div>
        </div>
      )}
    </div>
  );
}
