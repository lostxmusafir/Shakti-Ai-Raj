"use client";

import { cn } from "@/lib/cn";

export function Loader({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1", className)} aria-label="Loading">
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400"
          style={{ animationDelay: `${index * 120}ms`, animationDuration: "900ms" }}
        />
      ))}
    </span>
  );
}

export function Shimmer({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "text-slate-300",
        className,
      )}
    >
      {children}
    </span>
  );
}

export default Loader;
