"use client";

import { createContext, useContext, useState, useCallback, useEffect } from "react";

export interface TenantContextType {
  tenantId: string;
  setTenantId: (id: string) => void;
}

export const TenantContext = createContext<TenantContextType>({
  tenantId: "default",
  setTenantId: () => {},
});

export function useTenant() {
  return useContext(TenantContext);
}

export function useTenantState(): TenantContextType {
  const [tenantId, setTenantIdState] = useState<string>("default");

  useEffect(() => {
    const stored = localStorage.getItem("tenantId");
    if (stored) {
      setTenantIdState(stored);
    }
  }, []);

  const setTenantId = useCallback((id: string) => {
    setTenantIdState(id);
    localStorage.setItem("tenantId", id);
  }, []);

  return { tenantId, setTenantId };
}
