import { cn } from "@/lib/utils";
import { HTMLAttributes } from "react";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "secondary" | "destructive" | "outline" | "success" | "warning";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        {
          "bg-primary text-primary-foreground": variant === "default",
          "bg-secondary text-secondary-foreground": variant === "secondary",
          "bg-destructive text-destructive-foreground": variant === "destructive",
          "border border-border text-foreground": variant === "outline",
          "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400": variant === "success",
          "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400": variant === "warning",
        },
        className
      )}
      {...props}
    />
  );
}
