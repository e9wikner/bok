"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { TenantContext, useTenantState } from "@/hooks/useTenant";

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      })
  );

  const tenantState = useTenantState();

  return (
    <QueryClientProvider client={queryClient}>
      <TenantContext.Provider value={tenantState}>
        {children}
      </TenantContext.Provider>
    </QueryClientProvider>
  );
}
