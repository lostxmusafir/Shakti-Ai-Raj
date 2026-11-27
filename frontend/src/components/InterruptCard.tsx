"use client";

import { useRef, useState, type FormEvent } from "react";
import { CheckCircle2, HelpCircle, ShieldAlert, XCircle } from "lucide-react";
import type { PendingInterruptPayload } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  canTriggerInterruptAction,
  shouldRenderInlineCancel,
  validateFreeTextInput,
} from "@/lib/interrupt";

interface InterruptCardProps {
  interrupt: PendingInterruptPayload;
  submitting?: boolean;
  resolvedLabel?: string | null;
  cancelled?: boolean;
  onSubmit: (response: string) => Promise<void> | void;
  onCancel?: () => Promise<void> | void;
}

export default function InterruptCard({
  interrupt,
  submitting = false,
  resolvedLabel = null,
  cancelled = false,
  onSubmit,
  onCancel,
}: InterruptCardProps) {
  const [freeText, setFreeText] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const actionLockRef = useRef(false);

  const isDone = Boolean(resolvedLabel) || cancelled;
  const isConfirmation = interrupt.type === "confirmation";
  const options = interrupt.options ?? [];
  const showChoiceCancel = shouldRenderInlineCancel({
    type: interrupt.type,
    hasCancelHandler: Boolean(onCancel),
    options,
  });

  const handleOptionClick = async (optionId: string) => {
    if (!canTriggerInterruptAction({ submitting, isDone, actionLocked: actionLockRef.current })) {
      return;
    }
    actionLockRef.current = true;
    setLocalError(null);
    try {
      await onSubmit(optionId);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Failed to submit clarification.");
    } finally {
      actionLockRef.current = false;
    }
  };

  const handleFreeTextSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canTriggerInterruptAction({ submitting, isDone, actionLocked: actionLockRef.current })) {
      return;
    }
    const validation = validateFreeTextInput(freeText);
    if (!validation.valid) {
      setLocalError(validation.error);
      return;
    }
    actionLockRef.current = true;
    setLocalError(null);
    try {
      await onSubmit(validation.value);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Failed to submit clarification.");
    } finally {
      actionLockRef.current = false;
    }
  };

  const handleCancelClick = async () => {
    if (!onCancel || !canTriggerInterruptAction({ submitting, isDone, actionLocked: actionLockRef.current })) {
      return;
    }
    actionLockRef.current = true;
    setLocalError(null);
    try {
      await onCancel();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Failed to cancel clarification.");
    } finally {
      actionLockRef.current = false;
    }
  };

  return (
    <div
      aria-busy={submitting}
      className={cn(
        "rounded-xl border px-4 py-3.5 text-[13px] transition",
        cancelled
          ? "border-slate-800 bg-slate-900/40 text-slate-400"
          : resolvedLabel
          ? "border-emerald-500/30 bg-emerald-500/[0.05] text-slate-200"
          : isConfirmation
          ? "border-amber-500/35 bg-amber-500/[0.06] text-slate-100"
          : "border-indigo-500/35 bg-indigo-500/[0.06] text-slate-100",
      )}
    >
      <div className="flex items-start gap-2.5">
        {cancelled ? (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
        ) : resolvedLabel ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        ) : isConfirmation ? (
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
        ) : (
          <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
        )}

        <div className="min-w-0 flex-1 space-y-2.5">
          <div className="text-[11.5px] font-medium text-slate-400">
            {cancelled
              ? "Clarification cancelled"
              : resolvedLabel
              ? `✓ ${resolvedLabel} selected`
              : "I need one detail before I can calculate this."}
          </div>

          <div className="font-medium leading-snug text-slate-100">{interrupt.question}</div>

          {!isDone && interrupt.type === "free_text" ? (
            <form onSubmit={handleFreeTextSubmit} className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={freeText}
                onChange={(e) => {
                  setFreeText(e.target.value);
                  if (localError) setLocalError(null);
                }}
                placeholder={interrupt.placeholder || "Type your answer..."}
                aria-label={interrupt.question}
                aria-invalid={Boolean(localError)}
                disabled={submitting || isDone}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-[12.5px] text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={submitting || isDone}
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-[12px] font-medium text-white transition hover:bg-indigo-500 disabled:opacity-50"
              >
                {submitting ? "Resuming..." : "Continue"}
              </button>
              {onCancel ? (
                <button
                  type="button"
                  disabled={submitting || isDone}
                  onClick={() => handleCancelClick()}
                  className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-[12px] text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 disabled:opacity-50"
                >
                  Cancel
                </button>
              ) : null}
            </form>
          ) : null}

          {!isDone && (interrupt.type === "choice" || interrupt.type === "confirmation") ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {options.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  disabled={submitting || isDone}
                  onClick={() => handleOptionClick(opt.id)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-[12px] font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
                    opt.id === "cancel"
                      ? "border-slate-700 bg-slate-900/60 text-slate-300 hover:border-slate-600 hover:bg-slate-800"
                      : isConfirmation && opt.id === "approve"
                      ? "border-amber-500/40 bg-amber-500/15 text-amber-200 hover:bg-amber-500/25"
                      : "border-indigo-500/40 bg-indigo-500/15 text-indigo-200 hover:bg-indigo-500/25",
                  )}
                >
                  {opt.label}
                </button>
              ))}
              {showChoiceCancel && onCancel ? (
                <button
                  type="button"
                  disabled={submitting || isDone}
                  onClick={() => handleCancelClick()}
                  className="rounded-lg border border-slate-700 px-2.5 py-1.5 text-[12px] text-slate-400 transition hover:bg-slate-800 hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Cancel
                </button>
              ) : null}
            </div>
          ) : null}

          {localError ? (
            <div role="alert" className="text-[11.5px] text-red-400">
              {localError}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
