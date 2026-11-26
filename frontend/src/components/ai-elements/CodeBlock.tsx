"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/cn";

export function CodeBlock({
  code,
  language,
  className,
}: {
  code: string;
  language?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className={cn("group my-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-950/70", className)}>
      <div className="flex items-center justify-between border-b border-slate-800/80 px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-wide text-slate-500">{language || "code"}</span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-slate-400 transition hover:bg-slate-800 hover:text-slate-200"
          aria-label="Copy code"
        >
          {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-3 py-2.5 text-[12px] leading-5">
        <code className="font-mono text-slate-200">{code}</code>
      </pre>
    </div>
  );
}

export default CodeBlock;
