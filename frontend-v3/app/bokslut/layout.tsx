import Link from "next/link";
import { FileText, ReceiptText } from "lucide-react";

export const metadata = {
  title: "Bokslut - BokAi",
};

export default function BokslutLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="border-b bg-background/80 px-4 py-3 lg:px-8">
        <nav className="mx-auto flex max-w-[1400px] flex-wrap gap-2">
          <Link
            href="/bokslut/ink2"
            className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <FileText className="h-4 w-4" />
            Inkomstdeklaration 2
          </Link>
          <Link
            href="/bokslut/moms"
            className="inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ReceiptText className="h-4 w-4" />
            Momsdeklaration
          </Link>
        </nav>
      </div>
      {children}
    </div>
  );
}
