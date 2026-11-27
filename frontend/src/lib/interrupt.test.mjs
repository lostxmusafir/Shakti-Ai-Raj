import test from "node:test";
import assert from "node:assert/strict";
import {
  canTriggerInterruptAction,
  classifyPollStatus,
  resolveInterruptOutcome,
  shouldRenderInlineCancel,
  shouldRetryPoll,
  validateFreeTextInput,
} from "./interrupt.ts";

test("validateFreeTextInput rejects empty and whitespace-only strings", () => {
  assert.deepEqual(validateFreeTextInput(""), {
    valid: false,
    error: "Please enter a value before continuing.",
  });
  assert.deepEqual(validateFreeTextInput("   \t\n  "), {
    valid: false,
    error: "Please enter a value before continuing.",
  });
});

test("validateFreeTextInput trims valid input", () => {
  assert.deepEqual(validateFreeTextInput("  Record Date  "), {
    valid: true,
    value: "Record Date",
  });
});

test("canTriggerInterruptAction enforces submitting, isDone, and synchronous lock", () => {
  assert.equal(canTriggerInterruptAction({ submitting: false, isDone: false, actionLocked: false }), true);
  assert.equal(canTriggerInterruptAction({ submitting: true, isDone: false, actionLocked: false }), false);
  assert.equal(canTriggerInterruptAction({ submitting: false, isDone: true, actionLocked: false }), false);
  assert.equal(canTriggerInterruptAction({ submitting: false, isDone: false, actionLocked: true }), false);
});

test("resolveInterruptOutcome preserves pending interrupt on idempotent_replay without interrupt payload", () => {
  assert.deepEqual(
    resolveInterruptOutcome({ status: "interrupted", idempotent_replay: true }),
    { kind: "keep_interrupt" },
  );

  const next = { interrupt_id: "intr-2", type: "choice", options: [{ id: "a", label: "A" }] };
  assert.deepEqual(
    resolveInterruptOutcome({ status: "interrupted", interrupt: next }),
    { kind: "next_interrupt", interrupt: next },
  );

  assert.deepEqual(resolveInterruptOutcome({ status: "cancelled" }), { kind: "cancelled" });
  assert.deepEqual(resolveInterruptOutcome({ status: "failed", error: "boom" }), { kind: "failed" });
  assert.deepEqual(resolveInterruptOutcome({ status: "completed" }), { kind: "completed" });
});

test("classifyPollStatus maps terminal, paused, and in-progress statuses", () => {
  assert.equal(classifyPollStatus("interrupted"), "interrupted");
  assert.equal(classifyPollStatus("cancelled"), "cancelled");
  assert.equal(classifyPollStatus("completed"), "completed");
  assert.equal(classifyPollStatus("failed"), "failed");
  assert.equal(classifyPollStatus("queued"), "active");
  assert.equal(classifyPollStatus("executing"), "active");
});

test("shouldRenderInlineCancel renders for choice without cancel option and free_text, not confirmation", () => {
  assert.equal(
    shouldRenderInlineCancel({
      type: "choice",
      hasCancelHandler: true,
      options: [{ id: "record_date" }, { id: "incident_time" }],
    }),
    true,
  );
  assert.equal(
    shouldRenderInlineCancel({
      type: "choice",
      hasCancelHandler: true,
      options: [{ id: "record_date" }, { id: "cancel" }],
    }),
    false,
  );
  assert.equal(
    shouldRenderInlineCancel({
      type: "choice",
      hasCancelHandler: false,
      options: [{ id: "record_date" }],
    }),
    false,
  );
  assert.equal(
    shouldRenderInlineCancel({
      type: "confirmation",
      hasCancelHandler: true,
      options: [{ id: "approve" }, { id: "cancel" }],
    }),
    false,
  );
  assert.equal(
    shouldRenderInlineCancel({
      type: "free_text",
      hasCancelHandler: true,
    }),
    true,
  );
});

test("shouldRetryPoll stops immediately on fatal 401/403/404 statuses", () => {
  assert.equal(shouldRetryPoll(401, 0), false);
  assert.equal(shouldRetryPoll(403, 0), false);
  assert.equal(shouldRetryPoll(404, 0), false);
});

test("shouldRetryPoll retries transient 5xx and network errors up to maxFailures", () => {
  assert.equal(shouldRetryPoll(502, 0), true);
  assert.equal(shouldRetryPoll(503, 3), true);
  assert.equal(shouldRetryPoll(502, 4), false);

  assert.equal(shouldRetryPoll(null, 0), true);
  assert.equal(shouldRetryPoll(undefined, 3), true);
  assert.equal(shouldRetryPoll(null, 4), false);

  assert.equal(shouldRetryPoll(500, 1, 2), true);
  assert.equal(shouldRetryPoll(500, 2, 2), false);
});
