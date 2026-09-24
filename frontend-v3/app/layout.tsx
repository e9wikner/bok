import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Providers } from "./providers";
import AuthGuard from "@/components/AuthGuard";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});

// Geist Mono bär varje belopp, datum och verifikationsnummer i skalet.
// Filen har legat i repot oladdad; utan den faller designen på första raden.
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "BokAi - Bokföringssystem",
  description: "Modernt bokföringssystem för svenska företag",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="sv" suppressHydrationWarning>
      <body className={`${geistSans.variable} ${geistMono.variable} font-sans antialiased`}>
        <Providers>
          <AuthGuard>
            <AppShell>{children}</AppShell>
          </AuthGuard>
        </Providers>
      </body>
    </html>
  );
}

function AppShell({ children }: { children: React.ReactNode }) {
  // Public pages (login) get rendered without the sidebar shell.
  // We use a client component for the conditional logic.
  return <AppShellClient>{children}</AppShellClient>;
}

// Client component so we can use usePathname
import AppShellClient from "@/components/AppShellClient";
