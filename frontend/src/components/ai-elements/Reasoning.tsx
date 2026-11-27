"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { cn } from "@/lib/cn";
import { Loader } from "@/components/ai-elements/Loader";

export interface ReasoningStep {
  id: string;
  label: string;
  state: "done" | "active" | "pending" | "failed";
}

/**
 * Compact execution/status steps. One line while working, expanding only to
 * the step list — never raw logs.
 */
export function Reasoning({
  title,
  steps,
  failed = false,
  className,
}: {
  title: string;
  steps: ReasoningStep[];
  failed?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-slate-800/80 bg-slate-900/40 px-3.5 py-2.5", className)}>
      <div className="flex items-center gap-2 text-[12px] font-medium text-slate-300">
        {failed ? (
          <XCircle className="h-3.5 w-3.5 text-red-400" />
        ) : (
          <Loader className="text-[var(--accent)]" />
        )}
        <span className={failed ? "text-red-300" : undefined}>{title}</span>
      </div>
      <ol className="mt-2 space-y-1.5">
        {steps.map((step) => (
          <li key={step.id} className="flex items-center gap-2 text-[11.5px]">
            <span className="flex h-3.5 w-3.5 items-center justify-center">
              {step.state === "done" ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400/90" />
              ) : step.state === "active" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[var(--accent)]" />
              ) : step.state === "failed" ? (
                <XCircle className="h-3.5 w-3.5 text-red-400" />
              ) : (
                <Circle className="h-3 w-3 text-slate-600" />
              )}
            </span>
            <span
              className={cn(
                step.state === "active" && "text-slate-200",
                step.state === "done" && "text-slate-400",
                step.state === "pending" && "text-slate-500",
                step.state === "failed" && "text-red-300",
              )}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default Reasoning;
