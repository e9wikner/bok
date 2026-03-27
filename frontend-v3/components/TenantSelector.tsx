"use client";

import { useEffect, useState } from "react";
import { useTenant } from "@/hooks/useTenant";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";

interface Tenant {
  id: string;
  name: string;
  org_number?: string;
}

export default function TenantSelector() {
  const { tenantId, setTenantId } = useTenant();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    api
      .getTenants()
      .then((data: Tenant[]) => {
        setTenants(data);
        // If current tenantId isn't in the list, switch to first available
        if (data.length > 0 && !data.find((t) => t.id === tenantId)) {
          setTenantId(data[0].id);
        }
      })
      .catch(() => {
        setTenants([]);
      })
      .finally(() => setLoading(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading || tenants.length === 0) {
    return null;
  }

  // Single tenant: show company name as label (no dropdown)
  if (tenants.length === 1) {
    return (
      <div className="px-3 py-2.5 border-b border-border">
        <div className="flex items-center gap-2">
          <Building2 className="h-4 w-4 text-muted-foreground flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{tenants[0].name}</p>
            {tenants[0].org_number && (
              <p className="text-xs text-muted-foreground">{tenants[0].org_number}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Multiple tenants: show dropdown
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTenantId(e.target.value);
    // Invalidate all cached queries so data refreshes for the new tenant
    queryClient.invalidateQueries();
  };

  const currentTenant = tenants.find((t) => t.id === tenantId);

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
        {tenants.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
            {t.org_number ? ` (${t.org_number})` : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
