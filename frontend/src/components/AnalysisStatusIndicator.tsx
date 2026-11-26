"use client";

import Reasoning, { type ReasoningStep } from "@/components/ai-elements/Reasoning";

const STEPS = [
  { id: "understanding", label: "Understanding question" },
  { id: "planning", label: "Inspecting schema" },
  { id: "executing", label: "Running analysis" },
  { id: "verifying", label: "Verifying result" },
];

function activeIndex(status: string): number {
  switch (status) {
    case "created":
    case "queued":
    case "understanding":
    case "retrieving_context":
      return 0;
    case "planning":
    case "validating_plan":
      return 1;
    case "executing":
      return 2;
    case "verifying":
    case "generating_answer":
      return 3;
    case "completed":
      return 4;
    default:
      return 0;
  }
}

/**
 * Compact progress surface shown while an analysis runs. Replaced by the
 * answer itself once complete, so no pipeline log remains on screen.
 */
export default function AnalysisStatusIndicator({ status }: { status: string }) {
  const normalized = (status || "").toLowerCase();
  const failed = normalized === "failed" || normalized === "error";
  const index = activeIndex(normalized);

  const steps: ReasoningStep[] = STEPS.map((step, stepIndex) => ({
    id: step.id,
    label: step.label,
    state: failed
      ? stepIndex < index
        ? "done"
        : stepIndex === index
          ? "failed"
          : "pending"
      : stepIndex < index
        ? "done"
        : stepIndex === index
          ? "active"
          : "pending",
  }));

  return (
    <Reasoning
      title={failed ? "Analysis failed" : "Analysing your data"}
      steps={steps}
      failed={failed}
    />
  );
}
