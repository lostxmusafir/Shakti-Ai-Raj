"use client";

import { useState } from "react";
import { Table, ChevronLeft, ChevronRight, Download, Cpu } from "lucide-react";

interface ResultTableProps {
  columns: string[];
  rows: Record<string, any>[];
  durationMs?: number;
}

export default function ResultTable({ columns, rows, durationMs }: ResultTableProps) {
  const [page, setPage] = useState(1);
  const pageSize = 8;
  const totalPages = Math.ceil(rows.length / pageSize) || 1;
  const currentRows = rows.slice((page - 1) * pageSize, page * pageSize);

  if (!columns || columns.length === 0) return null;

  const exportCsv = () => {
    const headerLine = columns.join(",");
    const rowLines = rows.map((r) =>
      columns
        .map((c) => {
          const val = r[c] !== null && r[c] !== undefined ? String(r[c]) : "";
          return val.includes(",") ? `"${val.replace(/"/g, '""')}"` : val;
        })
        .join(",")
    );
    const csvContent = "data:text/csv;charset=utf-8," + [headerLine, ...rowLines].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `analysis_result_${Date.now()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="my-3 overflow-hidden rounded-2xl border border-synapse-border bg-synapse-raised shadow-card">
      {/* Table Header Bar */}
      <div className="flex items-center justify-between border-b border-synapse-border bg-synapse-surface/60 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-synapse-raised border border-synapse-border text-synapse-accent">
            <Table className="h-3.5 w-3.5" />
          </div>
          <span className="text-xs font-semibold text-synapse-text">
            Analytical Result
          </span>
          <span className="rounded-full bg-synapse-surface border border-synapse-border px-2 py-0.5 text-[10px] font-mono text-synapse-muted">
            {rows.length.toLocaleString()} records
          </span>
        </div>

        <div className="flex items-center gap-2.5">
          {durationMs !== undefined && (
            <span className="flex items-center gap-1 rounded-md bg-synapse-surface border border-synapse-border px-2 py-0.5 text-[10px] font-mono text-synapse-secondary">
              <Cpu className="h-3 w-3 text-synapse-accent" />
              DuckDB • {durationMs}ms
            </span>
          )}

          <button
            type="button"
            onClick={exportCsv}
            title="Export as CSV"
            className="flex items-center gap-1 rounded-lg border border-synapse-border bg-synapse-surface hover:bg-synapse-hover px-2 py-1 text-[11px] font-medium text-synapse-secondary hover:text-synapse-text transition-colors"
          >
            <Download className="h-3 w-3" />
            <span className="hidden sm:inline">CSV</span>
          </button>
        </div>
      </div>

      {/* Scrollable Data Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-synapse-border bg-synapse-surface/30 text-synapse-muted">
            <tr>
              <th className="w-12 px-3.5 py-2 text-center text-synapse-faint font-mono text-[10px]">#</th>
              {columns.map((col) => (
                <th key={col} className="px-3.5 py-2 font-medium text-synapse-secondary">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-synapse-border/40 font-mono text-synapse-text">
            {currentRows.map((row, idx) => (
              <tr key={idx} className="hover:bg-synapse-hover/50 transition-colors">
                <td className="px-3.5 py-2 text-center text-synapse-faint text-[10px]">
                  {(page - 1) * pageSize + idx + 1}
                </td>
                {columns.map((col) => (
                  <td key={col} className="px-3.5 py-2 text-xs">
                    {row[col] !== null && row[col] !== undefined ? (
                      String(row[col])
                    ) : (
                      <span className="text-synapse-faint italic font-sans text-[11px]">null</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-synapse-border bg-synapse-surface/40 px-4 py-2 text-xs text-synapse-muted">
          <span className="text-[11px]">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, rows.length)} of {rows.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page === 1}
              className="rounded-lg p-1 text-synapse-muted hover:text-synapse-text hover:bg-synapse-surface border border-transparent hover:border-synapse-border disabled:opacity-30 disabled:pointer-events-none transition-colors"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2 text-[11px] font-mono text-synapse-secondary">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
              disabled={page === totalPages}
              className="rounded-lg p-1 text-synapse-muted hover:text-synapse-text hover:bg-synapse-surface border border-transparent hover:border-synapse-border disabled:opacity-30 disabled:pointer-events-none transition-colors"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
