"use client";

import { useTenant } from "@/hooks/useTenant";
import { useMe } from "@/hooks/useAuth";
import { useQueryClient } from "@tanstack/react-query";
import { Building2, ChevronDown } from "lucide-react";
import { useState, useRef, useEffect } from "react";

export default function TenantSelectorCompact() {
  const { tenantId, setTenantId } = useTenant();
  const { tenants, loading } = useMe();
  const queryClient = useQueryClient();
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

  if (loading || !tenants || tenants.length === 0) return null;

  const current = tenants.find((t) => t.id === tenantId) ?? tenants[0];

  if (tenants.length === 1) {
    return (
      <div className="flex items-center gap-1 text-sm font-medium max-w-[140px]">
        <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="truncate">{current.name ?? current.id}</span>
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-sm font-medium rounded-md px-2 py-1.5 hover:bg-accent transition-colors max-w-[140px]"
      >
        <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
        <span className="truncate">{current.name ?? current.id}</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 w-52 rounded-lg border border-border bg-card shadow-lg py-1">
          {tenants.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTenantId(t.id);
                queryClient.invalidateQueries();
                setOpen(false);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-accent transition-colors ${
                t.id === tenantId ? "font-semibold text-primary" : ""
              }`}
            >
              <div className="truncate">{t.name ?? t.id}</div>
              {t.org_number && (
                <div className="text-xs text-muted-foreground truncate">{t.org_number}</div>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
