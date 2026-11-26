"use client";

import { ChevronRight, Database, FileSpreadsheet, Filter, Hash, ShieldCheck } from "lucide-react";
import type { AnswerProvenance, Row } from "@/lib/answer";
import { cn } from "@/lib/cn";
import { formatNumber, humanizeColumn } from "@/lib/format";

/**
 * Collapsible evidence: source file, sheet, row identifiers, query scope and
 * a small matched-row preview. Collapsed by default.
 */
export default function EvidencePanel({
  provenance,
  compiledSql,
  rows,
  count,
  open,
  onToggle,
  sourceNames,
}: {
  provenance: AnswerProvenance;
  compiledSql?: string;
  rows?: Row[];
  count: number;
  open: boolean;
  onToggle: () => void;
  sourceNames?: string[];
}) {
  const evidenceRows = provenance.evidence_rows ?? [];
  const whereClause = extractWhere(compiledSql);
  const sourceFiles = sourceNames?.length ? sourceNames : (provenance.source_files ?? []);
  const sheets = provenance.source_sheets ?? [];
  const preview = (rows ?? []).slice(0, 5);

  return (
    <div className="overflow-hidden rounded-lg border border-slate-800/70 bg-slate-900/30">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11.5px] text-slate-400 transition hover:bg-slate-900/60 hover:text-slate-200"
      >
        <ChevronRight className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")} />
        <ShieldCheck className="h-3.5 w-3.5 text-slate-500" />
        <span className="font-medium">Evidence</span>
        <span className="text-[10.5px] text-slate-500">{formatNumber(count)} rows</span>
      </button>

      {open ? (
        <div className="space-y-3 border-t border-slate-800/70 px-3 py-2.5 text-[11px] text-slate-400">
          <div className="grid gap-2 sm:grid-cols-2">
            <Field icon={<Database className="h-3 w-3" />} label="Source files">
              {sourceFiles.length ? sourceFiles.map((file) => String(file)).join(", ") : "Not recorded"}
            </Field>
            <Field icon={<FileSpreadsheet className="h-3 w-3" />} label="Sheet">
              {sheets.length ? sheets.join(", ") : "—"}
            </Field>
            <Field icon={<Hash className="h-3 w-3" />} label="Rows analysed">
              {provenance.source_row_count !== undefined ? formatNumber(Number(provenance.source_row_count)) : "—"}
            </Field>
            <Field icon={<Filter className="h-3 w-3" />} label="Matched rows">
              {provenance.matched_row_count !== undefined ? formatNumber(Number(provenance.matched_row_count)) : formatNumber(count)}
            </Field>
          </div>

          <div>
            <div className="mb-1 text-slate-500">Applied filters</div>
            {whereClause ? (
              <code className="block overflow-x-auto rounded bg-slate-950/60 px-2 py-1.5 font-mono text-[10.5px] text-slate-300">
                WHERE {whereClause}
              </code>
            ) : (
              <div className="text-slate-500">None recorded for this query.</div>
            )}
          </div>

          {evidenceRows.length ? (
            <div>
              <div className="mb-1 text-slate-500">Row identifiers</div>
              <div className="flex flex-wrap gap-1">
                {evidenceRows.slice(0, 24).map((rowId) => (
                  <span
                    key={rowId}
                    className="rounded bg-slate-800/80 px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
                  >
                    #{rowId}
                  </span>
                ))}
                {evidenceRows.length > 24 ? (
                  <span className="self-center text-[10px] text-slate-500">+{evidenceRows.length - 24} more</span>
                ) : null}
              </div>
            </div>
          ) : null}

          {preview.length ? (
            <div>
              <div className="mb-1 text-slate-500">Matched rows</div>
              <div className="space-y-1">
                {preview.map((row, index) => (
                  <div key={index} className="truncate rounded bg-slate-950/50 px-2 py-1 font-mono text-[10px] text-slate-400">
                    {Object.entries(row)
                      .slice(0, 5)
                      .map(([key, value]) => `${humanizeColumn(key)}=${value === null ? "null" : String(value)}`)
                      .join("  ·  ")}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Field({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1 text-slate-500">
        {icon}
        <span>{label}</span>
      </div>
      <div className="truncate text-slate-300" title={typeof children === "string" ? children : undefined}>
        {children}
      </div>
    </div>
  );
}

function extractWhere(sql?: string): string | null {
  if (!sql) return null;
  const match = sql.match(/\bwhere\b([\s\S]*?)(?:\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)/i);
  const clause = match?.[1]?.trim();
  if (!clause) return null;
  return clause.replace(/\s+/g, " ");
}
