"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
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

  const authState = useAuthState();

  return (
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={authState}>
        {children}
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}
