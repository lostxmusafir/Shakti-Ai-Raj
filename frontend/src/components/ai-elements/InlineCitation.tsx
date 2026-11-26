"use client";

import { FileSpreadsheet } from "lucide-react";
import { cn } from "@/lib/cn";
import { formatNumber, shortFileName } from "@/lib/format";

/**
 * Compact source citation chips. Clicking one reveals the evidence panel
 * instead of navigating away.
 */
export function InlineCitation({
  name,
  rows,
  index,
  onOpen,
}: {
  name: string;
  rows?: number | null;
  index?: number;
  onOpen?: () => void;
}) {
  const content = (
    <>
      {index !== undefined ? (
        <span className="rounded bg-slate-800 px-1 text-[9px] font-semibold text-slate-400">{index}</span>
      ) : (
        <FileSpreadsheet className="h-3 w-3 text-indigo-300/80" />
      )}
      <span className="max-w-[180px] truncate">{shortFileName(name, 34)}</span>
      {rows !== undefined && rows !== null ? (
        <span className="text-[10px] text-slate-500">{formatNumber(rows)} rows</span>
      ) : null}
    </>
  );

  const className = cn(
    "inline-flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-900/60 px-1.5 py-0.5 text-[11px] text-slate-400",
    onOpen && "transition hover:border-slate-700 hover:text-slate-200",
  );

  if (!onOpen) return <span className={className}>{content}</span>;

  return (
    <button type="button" onClick={onOpen} title={`Show evidence from ${name}`} className={className}>
      {content}
    </button>
  );
}

export function Sources({
  items,
  onOpen,
  className,
}: {
  items: { name: string; rows?: number | null }[];
  onOpen?: () => void;
  className?: string;
}) {
  if (!items.length) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500", className)}>
      <span className="mr-0.5">Sources</span>
      {items.map((item, index) => (
        <InlineCitation key={`${item.name}-${index}`} name={item.name} rows={item.rows} onOpen={onOpen} />
      ))}
    </div>
  );
}

export default InlineCitation;
