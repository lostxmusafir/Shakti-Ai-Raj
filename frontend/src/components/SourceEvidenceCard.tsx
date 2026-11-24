"use client";

import { useState } from "react";
import { ShieldCheck, ChevronDown, ChevronUp, Fingerprint, FileText, CheckCircle2 } from "lucide-react";

interface EvidenceProps {
  provenance: {
    source_files?: string[];
    source_sheets?: string[];
    evidence_rows?: number[];
    policy_code?: string;
    policy_version?: number;
    query_hash?: string;
    result_hash?: string;
    verification_status?: string;
    source_row_count?: number;
    matched_row_count?: number;
  };
}

export default function SourceEvidenceCard({ provenance }: EvidenceProps) {
  const [expanded, setExpanded] = useState(false);

  if (!provenance) return null;
  const verified = provenance.verification_status?.toLowerCase() === "passed";

  return (
    <div className="my-2.5 overflow-hidden rounded-xl border border-synapse-border bg-synapse-surface/80 shadow-subtle transition-all">
      <div
        className="flex cursor-pointer items-center justify-between px-3.5 py-2.5 hover:bg-synapse-raised/60 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 text-xs">
          <ShieldCheck className="h-4 w-4 text-synapse-accent" />
          <span className="font-medium text-synapse-text">Verification & Evidence</span>
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium border ${
              verified
                ? "bg-emerald-950/50 text-emerald-300 border-emerald-800/40"
                : "bg-amber-950/50 text-amber-300 border-amber-800/40"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${verified ? "bg-emerald-400" : "bg-amber-400"}`} />
            {provenance.verification_status || "PASSED"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {provenance.evidence_rows && provenance.evidence_rows.length > 0 && (
            <span className="text-[11px] font-mono text-synapse-muted hidden sm:inline">
              {provenance.evidence_rows.length} evidence rows
            </span>
          )}
          <button
            type="button"
            className="rounded p-0.5 text-synapse-muted hover:text-synapse-text"
            aria-label="Toggle evidence details"
          >
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-synapse-border/60 bg-synapse-raised/50 px-3.5 py-3 text-xs text-synapse-secondary space-y-2.5 animate-in fade-in duration-150">
          {(provenance.source_row_count !== undefined || provenance.matched_row_count !== undefined) && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-synapse-muted">Source Rows:</span>{" "}
                <span className="font-mono text-synapse-text">{provenance.source_row_count ?? "—"}</span>
              </div>
              <div>
                <span className="text-synapse-muted">Matched Rows:</span>{" "}
                <span className="font-mono text-synapse-text">{provenance.matched_row_count ?? "—"}</span>
              </div>
            </div>
          )}

          {provenance.policy_code && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-synapse-muted">Policy Citation:</span>
              <span className="rounded bg-synapse-surface border border-synapse-border px-2 py-0.5 font-mono text-synapse-accent">
                {provenance.policy_code} (v{provenance.policy_version || 1})
              </span>
            </div>
          )}

          {provenance.evidence_rows && provenance.evidence_rows.length > 0 && (
            <div>
              <span className="text-synapse-muted block mb-1">Offending Source Row Indices:</span>
              <div className="flex flex-wrap gap-1">
                {provenance.evidence_rows.slice(0, 16).map((rowIdx) => (
                  <span
                    key={rowIdx}
                    className="rounded bg-red-950/40 border border-red-800/30 px-1.5 py-0.5 font-mono text-[10px] text-red-300"
                  >
                    Row {rowIdx}
                  </span>
                ))}
                {provenance.evidence_rows.length > 16 && (
                  <span className="text-[10px] text-synapse-faint self-center">
                    +{provenance.evidence_rows.length - 16} more
                  </span>
                )}
              </div>
            </div>
          )}

          {provenance.query_hash && (
            <div className="flex items-center gap-1.5 text-[11px] text-synapse-muted pt-1 border-t border-synapse-border/40">
              <Fingerprint className="h-3.5 w-3.5 text-synapse-faint" />
              <span>Query Hash:</span>
              <span className="font-mono text-[10px] text-synapse-secondary">
                {provenance.query_hash.slice(0, 18)}...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
