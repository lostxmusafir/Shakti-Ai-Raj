/**
 * Presentation helpers: turn backend column aliases into human labels and
 * format values without inventing information.
 */

const COLUMN_LABELS: Record<string, string> = {
  record_count: "Records",
  row_count: "Rows",
  total_rows: "Rows",
  n: "Count",
  cnt: "Count",
  count: "Count",
  agg_0: "Value",
  agg_1: "Value",
  debit_entries: "Debit entries",
  credit_entries: "Credit entries",
  total_incidents: "Incidents",
  external_incidents: "External incidents",
  internal_incidents: "Internal incidents",
  blocked_events: "Blocked incidents",
  blocked_incidents: "Blocked incidents",
  event_count: "Events",
  share_pct: "Share (%)",
  pct: "Share (%)",
  percentage: "Share (%)",
  incidents: "Incidents",
  total_gb: "Total data (GB)",
  data_mb: "Data (MB)",
  mb_sent: "Data sent (MB)",
  size_kb: "Size (KB)",
  total_sales: "Total sales",
  total_revenue: "Revenue",
  revenue: "Revenue",
  profit: "Profit",
  total_profit: "Total profit",
  unit_price: "Unit price",
  quantity: "Quantity",
  avg_value: "Average",
  avg_amount: "Average amount",
  avg_days: "Average days",
  processing_time: "Processing time",
  violation_count: "Violations",
  total_violations: "Violations",
  password_incidents: "Password file incidents",
  password_files_external: "Password files sent externally",
  cad_incidents: "CAD transfer incidents",
  peak_hour: "Peak hour",
  high_severity_personal: "High-severity personal webmail incidents",
  critical_count: "Critical incidents",
  yahoo_incidents: "Yahoo Mail incidents",
  mixed_incidents: "Mixed-recipient incidents",
  foreign_affiliate_transfers: "Foreign affiliate transfers",
  breaches: "Incidents",
  policy: "Policy",
  is_ext: "External",
  recipient_type: "Recipient type",
};

const AGGREGATE_PREFIXES = ["total_", "sum_", "avg_", "mean_", "min_", "max_", "count_distinct_"];

function titleCase(value: string): string {
  return value
    .split(" ")
    .filter(Boolean)
    .map((word) => (/^[A-Z0-9]{2,}$/.test(word) ? word : word.charAt(0).toUpperCase() + word.slice(1)))
    .join(" ");
}

/**
 * Human-readable label for a result column. Falls back to a title-cased,
 * underscore-free version of the alias so internal names never surface.
 */
export function humanizeColumn(raw: string): string {
  const key = String(raw ?? "").trim();
  if (!key) return "Value";

  const direct = COLUMN_LABELS[key] ?? COLUMN_LABELS[key.toLowerCase()];
  if (direct) return direct;

  const compact = key.replace(/\s+/g, "_").toLowerCase();
  if (COLUMN_LABELS[compact]) return COLUMN_LABELS[compact];

  // "total_Region" / "avg_grocery" -> "Region" / "Grocery"
  for (const prefix of AGGREGATE_PREFIXES) {
    if (compact.startsWith(prefix) && compact.length > prefix.length) {
      return titleCase(compact.slice(prefix.length).replace(/_/g, " "));
    }
  }

  // "count_of_orders" -> "Count of orders"
  if (compact.startsWith("count_") && compact.length > 6) {
    return titleCase(compact.replace(/_/g, " "));
  }

  return titleCase(compact.replace(/_/g, " "));
}

/** True when a label would be meaningless on its own ("Total Region"). */
export function isWeakLabel(label: string): boolean {
  return /^(Total|Value|Count|Sum|Avg)\s*$/i.test(label.trim());
}

export function isNumericValue(value: unknown): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string" && value.trim() !== "") {
    return /^-?\d+(\.\d+)?$/.test(value.trim());
  }
  return false;
}

export function toNumber(value: unknown): number {
  if (typeof value === "number") return value;
  return Number(String(value).trim());
}

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  const rounded = Math.abs(value) >= 1000 ? Math.round(value) : Math.round(value * 100) / 100;
  return rounded.toLocaleString("en-US", {
    maximumFractionDigits: Number.isInteger(rounded) ? 0 : 2,
  });
}

export interface FormattedValue {
  text: string;
  numeric: boolean;
  empty: boolean;
}

export function formatValue(value: unknown): FormattedValue {
  if (value === null || value === undefined || value === "") {
    return { text: "null", numeric: false, empty: true };
  }
  if (typeof value === "boolean") {
    return { text: value ? "Yes" : "No", numeric: false, empty: false };
  }
  if (isNumericValue(value)) {
    return { text: formatNumber(toNumber(value)), numeric: true, empty: false };
  }
  if (value instanceof Date) {
    return { text: value.toISOString().slice(0, 10), numeric: false, empty: false };
  }
  return { text: String(value), numeric: false, empty: false };
}

function escapeCsvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const header = columns.map(escapeCsvCell).join(",");
  const body = rows.map((row) => columns.map((column) => escapeCsvCell(row[column])).join(","));
  return [header, ...body].join("\n");
}

export function downloadText(filename: string, text: string, mime = "text/plain"): void {
  if (typeof window === "undefined") return;
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

export function formatDuration(ms?: number | null): string | null {
  if (ms === undefined || ms === null || !Number.isFinite(Number(ms))) return null;
  const value = Number(ms);
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

/** Short, human file name for attachment and citation chips. */
export function shortFileName(name?: string | null, max = 28): string {
  const value = (name || "Dataset").split("/").pop() || "Dataset";
  if (value.length <= max) return value;
  const dot = value.lastIndexOf(".");
  if (dot > 0 && value.length - dot < 8) {
    return `${value.slice(0, max - (value.length - dot) - 1)}…${value.slice(dot)}`;
  }
  return `${value.slice(0, max - 1)}…`;
}

export function fileKind(name?: string | null): string {
  const ext = (name || "").split(".").pop()?.toLowerCase();
  if (!ext || ext === name) return "FILE";
  if (["xlsx", "xls", "xlsm", "csv"].includes(ext)) return ext.toUpperCase();
  return ext.slice(0, 4).toUpperCase();
}
