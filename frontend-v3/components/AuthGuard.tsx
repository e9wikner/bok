"use client";

import { useAuth } from "@/hooks/useAuth";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";

const PUBLIC_PATHS = ["/login"];

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const isPublic = PUBLIC_PATHS.includes(pathname ?? "");

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated && !isPublic) {
      router.replace("/login");
    }
    if (isAuthenticated && isPublic) {
      router.replace("/");
    }
  }, [isAuthenticated, loading, isPublic, router]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  // Don't render protected routes while unauthenticated (avoid flash)
  if (!isAuthenticated && !isPublic) {
    return null;
  }

  return <>{children}</>;
}
