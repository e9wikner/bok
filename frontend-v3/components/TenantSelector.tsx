"use client";

import { useTenant } from "@/hooks/useTenant";
import { useMe } from "@/hooks/useAuth";
import { useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";

interface Tenant {
  id: string;
  name?: string;
  org_number?: string;
  role?: string;
}

export default function TenantSelector() {
  const { tenantId, setTenantId } = useTenant();
  const { tenants, loading } = useMe();
  const queryClient = useQueryClient();

  if (loading || !tenants || tenants.length === 0) {
    return null;
  }

  const typedTenants: Tenant[] = tenants;

  // Single tenant: show company name as label (no dropdown)
  if (typedTenants.length === 1) {
    return (
      <div className="px-3 py-2.5 border-b border-border">
        <div className="flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">
              {typedTenants[0].name ?? typedTenants[0].id}
            </p>
            {typedTenants[0].org_number && (
              <p className="text-xs text-muted-foreground">{typedTenants[0].org_number}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Multiple tenants: show dropdown
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTenantId(e.target.value);
    queryClient.invalidateQueries();
  };

  return (
    <div className="px-3 py-2.5 border-b border-border">
      <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground mb-1.5">
        <Building2 className="h-3.5 w-3.5" />
        Företag
      </label>
      <select
        value={tenantId}
        onChange={handleChange}
        className="w-full text-sm rounded-md border border-input bg-background px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-ring"
      >
        {typedTenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name ?? t.id}
            {t.org_number ? ` (${t.org_number})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
