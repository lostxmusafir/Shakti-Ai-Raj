/**
 * Turns a backend assistant message + result metadata into the pieces the
 * answer UI needs: clean narrative, a result view model, and verification
 * state. Rendering must never make an unverified answer look authoritative.
 */

import { formatNumber, formatValue, humanizeColumn, isNumericValue, toNumber } from "@/lib/format";

export type Row = Record<string, unknown>;

export interface AnswerResult {
  engine?: string;
  columns?: string[];
  rows?: Row[];
  row_count?: number;
  duration_ms?: number;
  compiled_sql?: string;
  [key: string]: unknown;
}

export interface AnswerProvenance {
  source_files?: string[];
  source_sheets?: string[];
  evidence_rows?: number[];
  policy_code?: string;
  policy_version?: number;
  query_hash?: string;
  result_hash?: string;
  verification_status?: string;
  source_row_count?: number;
  matched_row_count?: number;
  [key: string]: unknown;
}

export interface AnswerVerification {
  passed?: boolean;
  checks?: unknown;
  warnings?: string[];
  provenance?: AnswerProvenance;
  [key: string]: unknown;
}

export type VerificationState = "verified" | "failed" | "unverified";

export type ResultView =
  | { kind: "empty" }
  | { kind: "scalar"; label: string; value: string; numeric: boolean; context?: string; empty: boolean }
  | {
      kind: "metrics";
      items: { label: string; value: string; numeric: boolean; empty: boolean }[];
      context?: string;
    }
  | { kind: "table"; columns: { key: string; label: string }[]; rows: Row[] };

export interface ParsedAnswer {
  narrative: string;
  /** True when the backend only produced "Analysis results (1 records): **x**: 1". */
  isRawSummary: boolean;
  executionMs?: number;
  rowsAnalyzed?: number;
}

const EXECUTION_LINE =
  /^(?:\p{Extended_Pictographic}\s*)?\*\*(?:Verified DuckDB Execution|DuckDB Execution \(verification failed\)|Verified read-only Excel execution)\*\*/iu;
const VERIFICATION_LINE = /^Verification Status:\s*/i;
const RAW_SUMMARY = /^Analysis results \((\d+)\s+records?\):/i;

/**
 * Strip execution/verification footers from the stored answer so the UI can
 * present them as compact metadata, and detect the deterministic fallback
 * sentence that lists raw aliases.
 */
export function parseAnswer(content: string): ParsedAnswer {
  const text = (content || "").replace(/\r\n/g, "\n");
  const lines = text.split("\n");
  const narrativeLines: string[] = [];
  let executionMs: number | undefined;
  let rowsAnalyzed: number | undefined;

  for (const line of lines) {
    if (EXECUTION_LINE.test(line.trim())) {
      const duration = line.match(/([\d.]+)\s*ms/i);
      if (duration) executionMs = Number(duration[1]);
      const rows = line.match(/([\d,]+)\s*records?\s+analyzed/i);
      if (rows) rowsAnalyzed = Number(rows[1].replace(/,/g, ""));
      continue;
    }
    if (VERIFICATION_LINE.test(line.trim())) continue;
    narrativeLines.push(line);
  }

  let narrative = narrativeLines.join("\n").trim();
  let isRawSummary = false;

  if (RAW_SUMMARY.test(narrative)) {
    isRawSummary = true;
    narrative = "";
  }

  return { narrative, isRawSummary, executionMs, rowsAnalyzed };
}

function isIdentifierColumn(key: string): boolean {
  return /(^|_)(id|uuid|key|hash|code)$/i.test(key) && !/incident|policy|zip/i.test(key);
}

/**
 * Decide how the result should be presented. A single value is never a table.
 */
export function buildResultView(result?: AnswerResult | null): ResultView {
  const columns = Array.isArray(result?.columns) ? result!.columns.filter(Boolean) : [];
  const rows = Array.isArray(result?.rows) ? result!.rows : [];
  if (!columns.length || !rows.length) return { kind: "empty" };

  if (rows.length === 1) {
    const row = rows[0];
    const numericKeys = columns.filter((column) => isNumericValue(row[column]));
    const textKeys = columns.filter((column) => !isNumericValue(row[column]));

    // One measure with one descriptive dimension: a labelled metric, not a table.
    if (numericKeys.length === 1 && textKeys.length === 1) {
      const key = numericKeys[0];
      const value = formatValue(row[key]);
      return {
        kind: "scalar",
        label: humanizeColumn(key),
        value: value.text,
        numeric: value.numeric,
        empty: value.empty,
        context: `${humanizeColumn(textKeys[0])}: ${String(row[textKeys[0]] ?? "—")}`,
      };
    }

    // One measure only.
    if (numericKeys.length === 1 && textKeys.length === 0) {
      const key = numericKeys[0];
      const value = formatValue(row[key]);
      return { kind: "scalar", label: humanizeColumn(key), value: value.text, numeric: value.numeric, empty: value.empty };
    }

    // Two to four measures: compact comparison / metric grid.
    if (numericKeys.length >= 2 && numericKeys.length <= 4) {
      const context = textKeys
        .map((key) => `${humanizeColumn(key)}: ${String(row[key] ?? "—")}`)
        .find(() => true);
      return {
        kind: "metrics",
        items: numericKeys.map((key) => {
          const value = formatValue(row[key]);
          return { label: humanizeColumn(key), value: value.text, numeric: value.numeric, empty: value.empty };
        }),
        context,
      };
    }
  }

  const displayColumns = columns.filter((column) => !isIdentifierColumn(column) || columns.length <= 2);
  const selected = displayColumns.length ? displayColumns : columns;
  return {
    kind: "table",
    columns: selected.map((key) => ({ key, label: humanizeColumn(key) })),
    rows,
  };
}

/** Natural first line used only when the backend returned a raw alias dump. */
export function describeResult(view: ResultView, fallbackRows?: number): string {
  if (view.kind === "scalar") {
    return `**${view.value}** ${view.label.toLowerCase()}${view.context ? ` (${view.context})` : ""}.`;
  }
  if (view.kind === "metrics") {
    return view.items.map((item) => `**${item.label}:** ${item.value}`).join(" · ") + ".";
  }
  if (view.kind === "table") {
    const count = view.rows.length;
    return `Here are ${formatNumber(count)} rows from the verified result.`;
  }
  return fallbackRows ? `The query returned ${formatNumber(fallbackRows)} rows.` : "The query returned no rows.";
}

function checksPassed(checks: unknown): { total: number; failed: number } {
  if (!checks) return { total: 0, failed: 0 };
  const entries: { status?: string; passed?: boolean }[] = Array.isArray(checks)
    ? (checks as { status?: string; passed?: boolean }[])
    : Object.values(checks as Record<string, unknown>).filter(
        (value): value is { status?: string; passed?: boolean } => Boolean(value) && typeof value === "object",
      );
  let total = 0;
  let failed = 0;
  for (const entry of entries) {
    total += 1;
    const status = String(entry.status ?? "").toLowerCase();
    if (entry.passed === false || status === "failed" || status === "error") failed += 1;
  }
  return { total, failed };
}

export interface VerificationInfo {
  state: VerificationState;
  label: string;
  detail?: string;
  engine: string;
  durationLabel: string | null;
  rowLabel: string | null;
}

export function describeVerification(
  verification?: AnswerVerification | null,
  result?: AnswerResult | null,
  parsed?: ParsedAnswer,
): VerificationInfo {
  const provenance = verification?.provenance ?? {};
  const status = String(provenance.verification_status ?? "").toLowerCase();
  const passed = verification?.passed === true || (verification?.passed === undefined && status === "passed");
  const failedExplicitly = verification?.passed === false || status === "failed" || status === "error";
  const hasResult = Boolean(result?.rows?.length);

  const { failed } = checksPassed(verification?.checks);
  const state: VerificationState = passed ? "verified" : failedExplicitly || (hasResult && failed > 0) ? "failed" : "unverified";

  const engine = String(result?.engine || provenance.engine || "DuckDB");
  const engineLabel = /excel/i.test(engine) ? "Excel" : /duckdb/i.test(engine) ? "DuckDB" : engine;
  const duration = result?.duration_ms ?? parsed?.executionMs;
  const durationLabel = duration !== undefined && duration !== null && Number.isFinite(Number(duration))
    ? `${Math.round(Number(duration))} ms`
    : null;

  const rows =
    result?.row_count ?? parsed?.rowsAnalyzed ?? (result?.rows?.length ? result.rows.length : undefined);
  const rowLabel = rows !== undefined && rows !== null ? `${formatNumber(Number(rows))} ${Number(rows) === 1 ? "row" : "rows"}` : null;

  if (state === "verified") {
    return { state, label: "Verified", detail: "Result passed deterministic checks.", engine: engineLabel, durationLabel, rowLabel };
  }
  if (state === "failed") {
    return {
      state,
      label: "Could not verify this result reliably",
      detail: "The verification layer rejected these numbers. Treat them as provisional.",
      engine: engineLabel,
      durationLabel,
      rowLabel,
    };
  }
  return {
    state,
    label: "Not verified",
    detail: "No verification record was returned for this answer.",
    engine: engineLabel,
    durationLabel,
    rowLabel,
  };
}

export function evidenceRowCount(provenance?: AnswerProvenance, result?: AnswerResult | null): number {
  if (provenance?.matched_row_count !== undefined && provenance.matched_row_count !== null) {
    return Number(provenance.matched_row_count);
  }
  if (Array.isArray(provenance?.evidence_rows) && provenance!.evidence_rows!.length) {
    return provenance!.evidence_rows!.length;
  }
  if (result?.row_count !== undefined && result.row_count !== null) return Number(result.row_count);
  return result?.rows?.length ?? 0;
}

export function resultIsEmpty(result?: AnswerResult | null): boolean {
  return !result?.rows?.length;
}

/** Numeric cells are right-aligned; keep the raw value for the table body. */
export function cellValue(value: unknown): { text: string; numeric: boolean; empty: boolean } {
  if (typeof value === "number" || isNumericValue(value)) {
    const formatted = formatValue(value);
    return { text: formatted.text, numeric: true, empty: formatted.empty };
  }
  return formatValue(value);
}

export function numericSortValue(value: unknown): number {
  return isNumericValue(value) ? toNumber(value) : Number.NaN;
}
