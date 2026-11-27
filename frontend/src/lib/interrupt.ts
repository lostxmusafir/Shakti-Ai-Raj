export interface InterruptOptionLike {
  id: string;
  label?: string;
  value?: string;
}

export interface InterruptLike {
  interrupt_id: string;
  type: "choice" | "confirmation" | "free_text" | string;
  options?: InterruptOptionLike[];
}

export interface ResumeOutcomeInput<TInterrupt extends InterruptLike = InterruptLike> {
  status: string;
  interrupt?: TInterrupt | null;
  idempotent_replay?: boolean;
  error?: string;
}

export type ResolvedInterruptOutcome<TInterrupt extends InterruptLike = InterruptLike> =
  | { kind: "next_interrupt"; interrupt: TInterrupt }
  | { kind: "keep_interrupt" }
  | { kind: "cancelled" }
  | { kind: "failed" }
  | { kind: "completed" };

export type PollStatusKind = "interrupted" | "cancelled" | "completed" | "failed" | "active";

export function validateFreeTextInput(
  raw: string,
): { valid: true; value: string } | { valid: false; error: string } {
  const trimmed = raw.trim();
  if (!trimmed) {
    return { valid: false, error: "Please enter a value before continuing." };
  }
  return { valid: true, value: trimmed };
}

export function canTriggerInterruptAction(params: {
  submitting: boolean;
  isDone: boolean;
  actionLocked: boolean;
}): boolean {
  return !params.submitting && !params.isDone && !params.actionLocked;
}

export function shouldRenderInlineCancel(params: {
  type: "choice" | "confirmation" | "free_text" | string;
  hasCancelHandler: boolean;
  options?: ReadonlyArray<{ id: string }>;
}): boolean {
  if (!params.hasCancelHandler) return false;
  if (params.type === "free_text") return true;
  if (params.type === "choice") {
    return !(params.options ?? []).some((opt) => opt.id === "cancel");
  }
  return false;
}

export function resolveInterruptOutcome<TInterrupt extends InterruptLike>(
  res: ResumeOutcomeInput<TInterrupt>,
): ResolvedInterruptOutcome<TInterrupt> {
  if (res.status === "interrupted") {
    if (res.interrupt) {
      return { kind: "next_interrupt", interrupt: res.interrupt };
    }
    return { kind: "keep_interrupt" };
  }
  if (res.status === "cancelled") {
    return { kind: "cancelled" };
  }
  if (res.status === "failed") {
    return { kind: "failed" };
  }
  return { kind: "completed" };
}

export function classifyPollStatus(status: string): PollStatusKind {
  if (
    status === "interrupted" ||
    status === "cancelled" ||
    status === "completed" ||
    status === "failed"
  ) {
    return status;
  }
  return "active";
}

export function shouldRetryPoll(
  statusCode: number | null | undefined,
  failureCount: number,
  maxFailures = 4,
): boolean {
  if (statusCode === 401 || statusCode === 403 || statusCode === 404) {
    return false;
  }
  return failureCount < maxFailures;
}
