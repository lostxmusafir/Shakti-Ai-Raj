"use client";

import { useState, type ReactNode } from "react";
import { Check, Copy, Download } from "lucide-react";
import { cn } from "@/lib/cn";

export function ActionButton({
  label,
  onClick,
  icon,
  className,
}: {
  label: string;
  onClick: () => void;
  icon: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-slate-500 transition",
        "hover:bg-slate-800/60 hover:text-slate-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/30",
        className,
      )}
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}

export function Actions({
  text,
  onExport,
  className,
}: {
  text: string;
  onExport?: () => void;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className={cn("flex flex-wrap items-center gap-1 text-slate-500", className)}>
      <ActionButton
        label={copied ? "Copied" : "Copy"}
        onClick={copy}
        icon={copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      />
      {onExport ? (
        <ActionButton label="Export" onClick={onExport} icon={<Download className="h-3.5 w-3.5" />} />
      ) : null}
    </div>
  );
}

export default Actions;
