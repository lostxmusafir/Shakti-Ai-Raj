"use client";

import { CheckCircle2, CircleDashed, AlertCircle, Cpu } from "lucide-react";

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
    <div className="my-3 rounded-xl border border-slate-800 bg-slate-900/60 p-3.5 backdrop-blur-sm">
      <div className="flex items-center justify-between pb-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <Cpu className="h-4 w-4 text-indigo-400" />
          Analysis Orchestration Pipeline
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
            isFailed
              ? "bg-red-950 text-red-400 border border-red-800"
              : normalized === "completed"
              ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
              : "bg-indigo-950 text-indigo-400 border border-indigo-800 animate-pulse"
          }`}
        >
          {status}
        </span>
      </div>

      <div className="grid grid-cols-5 gap-1.5 pt-2">
        {STEPS.map((step, idx) => {
          const isDone = idx < currentIndex || normalized === "completed";
          const isCurrent = idx === currentIndex && normalized !== "completed" && !isFailed;
          return (
            <div
              key={step.id}
              className={`flex flex-col items-center rounded-lg p-1.5 text-center transition ${
                isDone
                  ? "bg-emerald-950/30 text-emerald-400"
                  : isCurrent
                  ? "bg-indigo-950/50 text-indigo-300 ring-1 ring-indigo-500/50"
                  : "bg-slate-800/20 text-slate-500"
              }`}
            >
              <div className="mb-1">
                {isDone ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                ) : isCurrent ? (
                  <CircleDashed className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                ) : (
                  <div className="h-3.5 w-3.5 rounded-full border border-slate-700" />
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
