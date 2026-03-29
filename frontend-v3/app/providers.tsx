"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { TenantContext, useTenantState } from "@/hooks/useTenant";
import { AuthContext, useAuthState } from "@/hooks/useAuth";

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
  const authState = useAuthState();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authState}>
        <TenantContext.Provider value={tenantState}>
          {children}
        </TenantContext.Provider>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}
