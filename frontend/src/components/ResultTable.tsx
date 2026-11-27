"use client";

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Table2 } from "lucide-react";
import { cellValue, type Row } from "@/lib/answer";
import { cn } from "@/lib/cn";
import { downloadText, formatNumber, toCsv } from "@/lib/format";

export interface ResultColumn {
  key: string;
  label: string;
}

function formatColumnHeader(col: string): string {
  const clean = col.toLowerCase().trim();
  const aliasMap: Record<string, string> = {
    n: "Count",
    cnt: "Count",
    agg_0: "Count",
    count_1: "Count",
    record_count: "Record Count",
    incident_count: "Incident Count",
    customer_count: "Customer Count",
    blocked_count: "Blocked Incidents",
    permitted_count: "Permitted Incidents",
    external_incidents: "External Email Incidents",
    external_email_incidents: "External Email Incidents",
    blocked_external_incidents: "Blocked External Incidents",
    debit_entries: "Debit Entries",
    credit_entries: "Credit Entries",
    total_size: "Total Size (KB)",
    total_gb: "Total Data (GB)",
    data_mb: "Data (MB)",
    size_kb: "Size (KB)",
    is_ext: "External",
    src: "Sender",
    dest: "Destination",
  };
  if (aliasMap[clean]) return aliasMap[clean];
  return col.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Tabular result surface. Only rendered for genuinely tabular answers
 * (more than one row); single values use the metric surfaces instead.
 */
export default function ResultTable({
  columns,
  rows,
  failed = false,
  pageSize = 10,
}: {
  columns: ResultColumn[];
  rows: Row[];
  failed?: boolean;
  pageSize?: number;
}) {
  const [page, setPage] = useState(1);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const currentRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);

  const numericColumns = useMemo(() => {
    const flags = new Set<string>();
    columns.forEach((column) => {
      const sample = rows.slice(0, 20).map((row) => row[column.key]);
      if (sample.length && sample.every((value) => value === null || value === undefined || typeof value === "number")) {
        flags.add(column.key);
      }
    });
    return flags;
  }, [columns, rows]);

  if (!columns.length) return null;

  const exportCsv = () => {
    downloadText("analysis-result.csv", toCsv(columns.map((column) => column.key), rows), "text/csv");
  };

  return (
    <div className={cn("data-table overflow-hidden rounded-lg border border-slate-800 bg-slate-900/50", failed && "border-amber-500/25")}>
      <div className="flex items-center justify-between border-b border-slate-800/80 px-3 py-1.5">
        <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
          <Table2 className="h-3.5 w-3.5 text-slate-500" />
          <span className="tabular-nums">{formatNumber(rows.length)} rows</span>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10.5px] text-slate-500 transition hover:bg-slate-800/60 hover:text-slate-200"
        >
          <Download className="h-3 w-3" />
          Export CSV
        </button>
      </div>

      <div className="max-h-[420px] overflow-auto">
          <table className="w-full border-collapse text-[12px]" aria-label="Analysis result table">
          <thead className="sticky top-0 z-10 text-slate-400">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "whitespace-nowrap border-b border-slate-800 px-3 py-2 text-left font-medium",
                    numericColumns.has(column.key) && "text-right",
                  )}
                >
                  {formatColumnHeader(column.label)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {currentRows.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-slate-800/50 last:border-0 hover:bg-slate-800/25">
                {columns.map((column) => {
                  const value = cellValue(row[column.key]);
                  return (
                    <td
                      key={column.key}
                      className={cn(
                        "max-w-[280px] truncate px-3 py-1.5 align-top text-slate-300",
                        value.numeric && "text-right tabular-nums",
                        value.empty && "italic text-slate-600",
                      )}
                      title={value.text}
                    >
                      {value.text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 ? (
        <div className="flex items-center justify-between border-t border-slate-800/80 px-3 py-1.5 text-[11px] text-slate-500">
          <span className="tabular-nums">
            {formatNumber((safePage - 1) * pageSize + 1)}–{formatNumber(Math.min(safePage * pageSize, rows.length))} of{" "}
            {formatNumber(rows.length)}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setPage(Math.max(1, safePage - 1))}
              disabled={safePage === 1}
              aria-label="Previous page"
              className="rounded p-1 transition hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30 disabled:hover:bg-transparent"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>
            <span className="tabular-nums">
              {safePage} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage(Math.min(totalPages, safePage + 1))}
              disabled={safePage === totalPages}
              aria-label="Next page"
              className="rounded p-1 transition hover:bg-slate-800 hover:text-slate-200 disabled:opacity-30 disabled:hover:bg-transparent"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
