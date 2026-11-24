"use client";

import { useState } from "react";
import { Table, ChevronLeft, ChevronRight, Hash } from "lucide-react";

interface ResultTableProps {
  columns: string[];
  rows: Record<string, any>[];
  durationMs?: number;
}

export default function ResultTable({ columns, rows, durationMs }: ResultTableProps) {
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const totalPages = Math.ceil(rows.length / pageSize) || 1;
  const currentRows = rows.slice((page - 1) * pageSize, page * pageSize);

  if (!columns || columns.length === 0) return null;

  if (rows.length === 1 && columns.length === 2 &&
      columns.includes("debit_entries") && columns.includes("credit_entries")) {
    return (
      <div className="my-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-900/90 text-xs text-slate-200">
        <div className="border-b border-slate-800 px-4 py-2.5 font-semibold">Transaction entries</div>
        <table className="w-full text-left">
          <thead className="bg-slate-800/60"><tr><th className="px-4 py-2">Type</th><th className="px-4 py-2">Entries</th></tr></thead>
          <tbody>
            <tr className="border-t border-slate-800"><td className="px-4 py-2">Debit</td><td className="px-4 py-2">{rows[0].debit_entries}</td></tr>
            <tr className="border-t border-slate-800"><td className="px-4 py-2">Credit</td><td className="px-4 py-2">{rows[0].credit_entries}</td></tr>
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
                  {col}
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
