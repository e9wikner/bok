"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { PUBLIC_PATHS_FOR_LAYOUT } from "@/lib/auth-config";

export default function AppShellClient({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS_FOR_LAYOUT.includes(pathname ?? "");

  if (isPublic) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 lg:min-h-screen">
        <div className="pt-14 pb-20 lg:pt-0 lg:pb-0">{children}</div>
      </main>
    </div>
  );
}
