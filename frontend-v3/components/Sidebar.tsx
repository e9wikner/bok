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
} from "lucide-react";
import { useDarkMode } from "@/hooks/useDarkMode";
import { useState } from "react";

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
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Mobile overlay */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-card border-b px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
            <Shield className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="font-bold text-lg">Bokio</span>
        </div>
        <button onClick={toggle} className="p-2 rounded-lg hover:bg-accent">
          {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile bottom nav — show key pages + settings */}
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
              <h1 className="font-bold text-lg leading-tight">Bokio</h1>
              <p className="text-xs text-muted-foreground">Bokföringssystem</p>
            </div>
          )}
        </div>

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
