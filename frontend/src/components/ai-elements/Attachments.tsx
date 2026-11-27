"use client";

import { FileSpreadsheet, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { fileKind, formatNumber, shortFileName } from "@/lib/format";

export interface AttachmentItem {
  id: string;
  name: string;
  rows?: number | null;
  state?: string | null;
}

/**
 * Attachment chips used by both the composer and sent user messages.
 * `onRemove` is only wired in the composer, preserving the existing lifecycle.
 */
export function Attachments({
  items,
  onRemove,
  className,
  compact = false,
}: {
  items: AttachmentItem[];
  onRemove?: (id: string) => void;
  className?: string;
  compact?: boolean;
}) {
  if (!items.length) return null;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {items.map((item) => (
        <span
          key={item.id}
          className={cn(
            "group inline-flex max-w-full items-center gap-2 rounded-lg border border-slate-700/70 bg-slate-900/70 px-2 py-1 text-[11px] text-slate-300",
            compact && "px-1.5 py-0.5",
          )}
          title={item.name}
        >
          <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
          <span className="truncate">{shortFileName(item.name)}</span>
          <span className="shrink-0 rounded bg-slate-800 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-slate-400">
            {fileKind(item.name)}
          </span>
          {item.rows !== undefined && item.rows !== null ? (
            <span className="shrink-0 text-[10px] text-slate-500">{formatNumber(item.rows)} rows</span>
          ) : null}
          {item.state && item.state !== "ready" ? (
            <span className="shrink-0 text-[10px] text-amber-400/90">{item.state.replace(/_/g, " ")}</span>
          ) : null}
          {onRemove ? (
            <button
              type="button"
              onClick={() => onRemove(item.id)}
              aria-label={`Remove ${item.name}`}
              className="-mr-0.5 rounded p-0.5 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
            >
              <X className="h-3 w-3" />
            </button>
          ) : null}
        </span>
      ))}
    </div>
  );
}

export default Attachments;
