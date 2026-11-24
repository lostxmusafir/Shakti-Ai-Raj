"use client";

import { CheckCircle2, CircleDashed, Cpu, Sparkles } from "lucide-react";

interface StatusProps {
  status: string;
}

const STEPS = [
  { id: "understanding", label: "Understanding Intent" },
  { id: "planning", label: "Planning Query" },
  { id: "executing", label: "Executing DuckDB" },
  { id: "verifying", label: "Verifying Result" },
  { id: "completed", label: "Verified & Complete" },
];

export default function AnalysisStatusIndicator({ status }: StatusProps) {
  const normalized = status.toLowerCase();

  const getStepIndex = (st: string) => {
    if (st === "created" || st === "queued" || st === "understanding") return 0;
    if (st === "retrieving_context" || st === "planning" || st === "validating_plan") return 1;
    if (st === "executing") return 2;
    if (st === "verifying" || st === "generating_answer") return 3;
    if (st === "completed") return 4;
    return 0;
  };

  const currentIndex = getStepIndex(normalized);
  const isFailed = normalized === "failed";

  return (
    <div className="my-3 overflow-hidden rounded-2xl border border-synapse-border bg-synapse-raised/90 p-4 shadow-subtle backdrop-blur-md animate-in fade-in duration-200">
      <div className="flex items-center justify-between pb-3 border-b border-synapse-border-subtle">
        <div className="flex items-center gap-2 text-xs font-semibold text-synapse-text">
          <Cpu className="h-4 w-4 text-synapse-accent animate-pulse" />
          <span>Deterministic Pipeline</span>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-mono uppercase tracking-wider border ${
            isFailed
              ? "bg-red-950/60 text-red-400 border-red-800/50"
              : normalized === "completed"
              ? "bg-emerald-950/60 text-emerald-400 border-emerald-800/50"
              : "bg-blue-950/60 text-blue-300 border-blue-800/50 animate-pulse"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${isFailed ? "bg-red-400" : normalized === "completed" ? "bg-emerald-400" : "bg-blue-400"}`} />
          {status}
        </span>
      </div>

      <div className="grid grid-cols-5 gap-2 pt-3">
        {STEPS.map((step, idx) => {
          const isDone = idx < currentIndex || normalized === "completed";
          const isCurrent = idx === currentIndex && normalized !== "completed" && !isFailed;

          return (
            <div
              key={step.id}
              className={`flex flex-col items-center rounded-xl p-2 text-center transition-colors border ${
                isDone
                  ? "bg-emerald-950/20 text-emerald-300 border-emerald-900/30"
                  : isCurrent
                  ? "bg-synapse-surface text-synapse-accent border-synapse-accent/40 shadow-subtle ring-1 ring-synapse-accent/20"
                  : "bg-synapse-surface/40 text-synapse-faint border-transparent"
              }`}
            >
              <div className="mb-1.5">
                {isDone ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                ) : isCurrent ? (
                  <CircleDashed className="h-3.5 w-3.5 animate-spin text-synapse-accent" />
                ) : (
                  <div className="h-3.5 w-3.5 rounded-full border border-synapse-border" />
                )}
              </div>
              <span className="text-[10px] font-medium leading-tight">
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
