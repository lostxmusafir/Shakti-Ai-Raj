"use client";

import { useState, type ReactNode } from "react";
import { ChevronRight, Wrench } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Collapsed technical surface (SQL, hashes, engine metadata).
 * Mirrors AI Elements' Tool disclosure: a quiet header row that expands.
 */
export function Tool({
  title,
  subtitle,
  children,
  defaultOpen = false,
  className,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={cn("overflow-hidden rounded-lg border border-slate-800/70 bg-slate-900/30", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11.5px] text-slate-400 transition hover:bg-slate-900/60 hover:text-slate-200"
      >
        <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 transition-transform", open && "rotate-90")} />
        <Wrench className="h-3.5 w-3.5 shrink-0 text-slate-500" />
        <span className="font-medium">{title}</span>
        {subtitle ? <span className="truncate text-[10.5px] text-slate-500">{subtitle}</span> : null}
      </button>
      {open ? <div className="border-t border-slate-800/70 px-3 py-2.5">{children}</div> : null}
    </div>
  );
}

export default Tool;
