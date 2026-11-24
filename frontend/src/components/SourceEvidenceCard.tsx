"use client";

import { useState } from "react";
import { ShieldCheck, FileText, ChevronDown, ChevronUp, Fingerprint, AlertTriangle } from "lucide-react";

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
    <div className="my-3 rounded-xl border border-indigo-900/40 bg-indigo-950/20 p-3 text-xs">
      <div
        className="flex cursor-pointer items-center justify-between"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 font-semibold text-indigo-300">
          <ShieldCheck className="h-4 w-4 text-indigo-400" />
          <span>Verification & Provenance Citations</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] border ${verified ? "bg-emerald-950/80 text-emerald-300 border-emerald-800" : "bg-amber-950/80 text-amber-300 border-amber-800"}`}>
            {provenance.verification_status || "UNKNOWN"}
          </span>
        </div>
        <button className="text-slate-400 hover:text-white">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-3 space-y-2 border-t border-indigo-900/30 pt-3 text-slate-300">
          {(provenance.source_row_count !== undefined || provenance.matched_row_count !== undefined) && (
            <div className="grid grid-cols-2 gap-2">
              <div><span className="font-medium text-slate-400">Source rows:</span> {provenance.source_row_count ?? "—"}</div>
              <div><span className="font-medium text-slate-400">Matched rows:</span> {provenance.matched_row_count ?? "—"}</div>
            </div>
          )}
          {provenance.policy_code && (
            <div className="flex items-center gap-2">
              <span className="font-medium text-slate-400">Policy Citation:</span>
              <span className="font-mono text-indigo-300">
                {provenance.policy_code} (v{provenance.policy_version || 1})
              </span>
            </div>
          )}

          {provenance.evidence_rows && provenance.evidence_rows.length > 0 && (
            <div>
              <span className="font-medium text-slate-400">Offending Row Evidence:</span>
              <div className="mt-1 flex flex-wrap gap-1">
                {provenance.evidence_rows.slice(0, 20).map((rowIdx) => (
                  <span
                    key={rowIdx}
                    className="rounded bg-red-950/60 px-1.5 py-0.5 font-mono text-[11px] text-red-300 border border-red-800/40"
                  >
                    Row {rowIdx}
                  </span>
                ))}
                {provenance.evidence_rows.length > 20 && (
                  <span className="text-[10px] text-slate-500 self-center">
                    +{provenance.evidence_rows.length - 20} more rows
                  </span>
                )}
              </div>
            </div>
          )}

          {provenance.query_hash && (
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <Fingerprint className="h-3.5 w-3.5 text-slate-500" />
              <span>Query Hash:</span>
              <span className="font-mono text-[10px] text-slate-300">
                {provenance.query_hash.slice(0, 16)}...
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
