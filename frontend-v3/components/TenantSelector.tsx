"use client";

import { useEffect, useState } from "react";
import { useTenant } from "@/hooks/useTenant";
import { api } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";

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
      .then((data: Tenant[]) => setTenants(data))
      .catch(() => {
        // Admin API not available or not in multi-tenant mode — hide selector
        setTenants([]);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading || tenants.length <= 1) {
    return null;
  }

  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTenantId(e.target.value);
    // Invalidate all cached queries so data refreshes for the new tenant
    queryClient.invalidateQueries();
  };

  return (
    <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
        Företag
      </label>
      <select
        value={tenantId}
        onChange={handleChange}
        className="w-full text-sm rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
