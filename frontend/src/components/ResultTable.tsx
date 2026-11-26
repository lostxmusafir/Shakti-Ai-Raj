"use client";

import { useState } from "react";
import { Table, ChevronLeft, ChevronRight, Hash } from "lucide-react";

interface ResultTableProps {
  columns: string[];
  rows: Record<string, any>[];
  durationMs?: number;
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

export default function ResultTable({ columns, rows, durationMs }: ResultTableProps) {
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const totalPages = Math.ceil(rows.length / pageSize) || 1;
  const currentRows = rows.slice((page - 1) * pageSize, page * pageSize);

  if (!columns || columns.length === 0) return null;

  // Single-row summary / comparative view
  if (rows.length === 1 && columns.length >= 2 && columns.every(c => typeof rows[0][c] === "number")) {
    return (
      <div className="my-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/90 text-xs text-slate-200">
        <div className="border-b border-slate-800 px-4 py-2.5 font-semibold flex items-center justify-between">
          <span>Comparative Metrics</span>
          {durationMs !== undefined && (
            <span className="text-[10px] text-slate-500 font-normal">
              Engine latency: {durationMs}ms
            </span>
          )}
        </div>
        <table className="w-full text-left">
          <thead className="bg-slate-800/60">
            <tr>
              <th className="px-4 py-2">Metric</th>
              <th className="px-4 py-2">Value</th>
            </tr>
          </thead>
          <tbody>
            {columns.map(col => (
              <tr key={col} className="border-t border-slate-800">
                <td className="px-4 py-2 text-slate-300">{formatColumnHeader(col)}</td>
                <td className="px-4 py-2 font-mono font-medium text-indigo-300">
                  {typeof rows[0][col] === "number" ? rows[0][col].toLocaleString() : String(rows[0][col])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/90 shadow-xl">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950/60 px-4 py-2.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <Table className="h-4 w-4 text-indigo-400" />
          Deterministic Result Table ({rows.length} rows)
        </div>
        {durationMs !== undefined && (
          <span className="text-[10px] text-slate-500">
            Engine latency: {durationMs}ms
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-800/60 text-slate-300">
            <tr>
              <th className="w-12 px-3 py-2 text-center text-slate-500">#</th>
              {columns.map((col) => (
                <th key={col} className="px-3 py-2 font-semibold">
                  {formatColumnHeader(col)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
            {currentRows.map((row, idx) => (
              <tr key={idx} className="hover:bg-slate-800/30">
                <td className="px-3 py-2 text-center text-slate-500 text-[10px]">
                  {(page - 1) * pageSize + idx + 1}
                </td>
                {columns.map((col) => (
                  <td key={col} className="px-3 py-2">
                    {row[col] !== null && row[col] !== undefined
                      ? String(row[col])
                      : <span className="text-slate-600 italic">null</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-slate-800 bg-slate-950/40 px-4 py-2 text-xs text-slate-400">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(p - 1, 1))}
              disabled={page === 1}
              className="rounded p-1 hover:bg-slate-800 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
              disabled={page === totalPages}
              className="rounded p-1 hover:bg-slate-800 disabled:opacity-40"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
