"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, CircleAlert, FileSpreadsheet, ShieldQuestion } from "lucide-react";
import MessageMarkdown from "@/components/ai-elements/MessageMarkdown";
import { Actions } from "@/components/ai-elements/Actions";
import { Sources } from "@/components/ai-elements/InlineCitation";
import { Tool } from "@/components/ai-elements/Tool";
import { CodeBlock } from "@/components/ai-elements/CodeBlock";
import ResultTable from "@/components/ResultTable";
import EvidencePanel from "@/components/SourceEvidenceCard";
import {
  buildResultView,
  describeResult,
  describeVerification,
  evidenceRowCount,
  parseAnswer,
  type AnswerProvenance,
  type AnswerResult,
  type AnswerVerification,
  type ResultView,
} from "@/lib/answer";
import { cn } from "@/lib/cn";
import { downloadText, toCsv } from "@/lib/format";

export interface KnownFile {
  id: string;
  original_name: string;
  row_count?: number | null;
}

export default function AnswerBody({
  content,
  result,
  verification,
  provenance,
  files = [],
  streaming = false,
  className,
}: {
  content: string;
  result?: AnswerResult | null;
  verification?: AnswerVerification | null;
  provenance?: AnswerProvenance | null;
  files?: KnownFile[];
  streaming?: boolean;
  className?: string;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const parsed = useMemo(() => parseAnswer(content || ""), [content]);
  const view = useMemo(() => buildResultView(result), [result]);
  const info = useMemo(() => describeVerification(verification, result, parsed), [verification, result, parsed]);
  const evidenceCount = useMemo(() => evidenceRowCount(provenance ?? verification?.provenance, result), [provenance, verification, result]);
  const sources = useMemo(() => {
    const ids = provenance?.source_files ?? verification?.provenance?.source_files ?? [];
    const resolved = ids.map((id) => {
      const match = files.find((file) => file.id === id);
      return { name: match?.original_name || "Dataset", rows: match?.row_count ?? null };
    });
    if (resolved.length) return resolved;
    return files.length === 1 ? [{ name: files[0].original_name, rows: files[0].row_count ?? null }] : [];
  }, [provenance, verification, files]);

  // While tokens are still arriving there is no result or verification yet;
  // showing those affordances would imply an answer that does not exist.
  if (streaming) {
    return <MessageMarkdown content={parsed.narrative} streaming className={className} />;
  }

  const narrative = parsed.isRawSummary || !parsed.narrative ? describeResult(view, result?.row_count) : parsed.narrative;
  const failed = info.state === "failed";

  const exportCsv = () => {
    if (view.kind === "table") {
      const raw = toCsv(view.columns.map((column) => column.key), view.rows);
      downloadText("analysis-result.csv", raw, "text/csv");
      return;
    }
    if (view.kind === "scalar" || view.kind === "metrics") {
      const items = view.kind === "scalar" ? [{ label: view.label, value: view.value }] : view.items;
      const raw = toCsv(["Metric", "Value"], items.map((item) => ({ Metric: item.label, Value: item.value })));
      downloadText("analysis-result.csv", raw, "text/csv");
    }
  };

  const copyText = [
    narrative.replace(/\*\*/g, "").replace(/`/g, ""),
    view.kind === "scalar" ? `${view.label}: ${view.value}` : "",
    view.kind === "metrics" ? view.items.map((item) => `${item.label}: ${item.value}`).join("; ") : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div className={cn("space-y-3", className)}>
      <MessageMarkdown content={narrative} streaming={streaming} />

      {failed ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-[12px] text-amber-200">
          <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-400" />
          <div>
            <div className="font-medium">{info.label}</div>
            <div className="mt-0.5 text-amber-200/70">{info.detail}</div>
          </div>
        </div>
      ) : null}

      {view.kind !== "empty" ? (
        <div className={cn(failed && "rounded-xl ring-1 ring-amber-500/20")}>
          <ResultSurface view={view} failed={failed} />
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium",
            info.state === "verified" && "bg-emerald-500/10 text-emerald-300",
            info.state === "failed" && "bg-amber-500/10 text-amber-300",
            info.state === "unverified" && "bg-slate-800/70 text-slate-400",
          )}
        >
          {info.state === "verified" ? (
            <CheckCircle2 className="h-3 w-3" />
          ) : info.state === "failed" ? (
            <AlertTriangle className="h-3 w-3" />
          ) : (
            <ShieldQuestion className="h-3 w-3" />
          )}
          {info.state === "verified" ? "Verified" : info.state === "failed" ? "Verification failed" : "Not verified"}
        </span>
        <span className="text-slate-500">{info.engine}</span>
        {info.durationLabel ? <span className="text-slate-600">•</span> : null}
        {info.durationLabel ? <span className="text-slate-500 tabular-nums">{info.durationLabel}</span> : null}
        {info.rowLabel ? <span className="text-slate-600">•</span> : null}
        {info.rowLabel ? <span className="text-slate-500 tabular-nums">{info.rowLabel}</span> : null}
      </div>

      <Sources items={sources} onOpen={evidenceCount ? () => setEvidenceOpen((value) => !value) : undefined} />

      {evidenceCount ? (
        <EvidencePanel
          provenance={provenance ?? verification?.provenance ?? {}}
          compiledSql={result?.compiled_sql}
          rows={view.kind === "table" ? view.rows : result?.rows}
          count={evidenceCount}
          open={evidenceOpen}
          onToggle={() => setEvidenceOpen((value) => !value)}
          sourceNames={sources.map((source) => source.name)}
        />
      ) : null}

      {(result?.compiled_sql || Object.keys(provenance ?? verification?.provenance ?? {}).length > 0) ? (
        <Tool title="Technical details" subtitle="SQL, hashes and engine metadata">
          <div className="space-y-2 text-[11px] text-slate-400">
            {result?.compiled_sql ? <CodeBlock code={result.compiled_sql} language="sql" /> : null}
            <dl className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              <Detail label="Engine" value={info.engine} />
              {info.durationLabel ? <Detail label="Execution" value={info.durationLabel} /> : null}
              {info.rowLabel ? <Detail label="Rows analysed" value={info.rowLabel} /> : null}
              {(provenance ?? verification?.provenance)?.query_hash ? (
                <Detail label="Query hash" value={String((provenance ?? verification?.provenance)?.query_hash).slice(0, 16)} mono />
              ) : null}
              {(provenance ?? verification?.provenance)?.result_hash ? (
                <Detail label="Result hash" value={String((provenance ?? verification?.provenance)?.result_hash).slice(0, 16)} mono />
              ) : null}
            </dl>
          </div>
        </Tool>
      ) : null}

      <Actions text={copyText} onExport={view.kind === "empty" ? undefined : exportCsv} />
    </div>
  );
}

function Detail({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="shrink-0 text-slate-500">{label}</dt>
      <dd className={cn("truncate text-slate-300", mono && "font-mono text-[10.5px]")}>{value}</dd>
    </div>
  );
}

function ResultSurface({ view, failed }: { view: ResultView; failed: boolean }) {
  if (view.kind === "scalar") {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
        <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{view.label}</div>
        <div
          className={cn(
            "mt-1 text-[26px] font-semibold leading-tight tracking-tight tabular-nums",
            view.empty ? "text-slate-500 italic" : "text-white",
            failed && !view.empty && "text-amber-100",
          )}
        >
          {view.empty ? "null" : view.value}
        </div>
        {view.context ? <div className="mt-0.5 text-[11px] text-slate-500">{view.context}</div> : null}
        {view.empty ? <div className="mt-1 text-[11px] text-slate-500">No value returned — this is not zero.</div> : null}
      </div>
    );
  }

  if (view.kind === "metrics") {
    return (
      <div className="space-y-1.5">
        <div className={cn("grid gap-2", view.items.length === 2 ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3")}>
          {view.items.map((item) => (
            <div key={item.label} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2.5">
              <div className="truncate text-[10.5px] font-medium uppercase tracking-wide text-slate-400" title={item.label}>
                {item.label}
              </div>
              <div
                className={cn(
                  "mt-0.5 text-[20px] font-semibold leading-tight tabular-nums",
                  item.empty ? "text-slate-500 italic" : "text-white",
                  failed && !item.empty && "text-amber-100",
                )}
              >
                {item.empty ? "null" : item.value}
              </div>
            </div>
          ))}
        </div>
        {view.context ? (
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <FileSpreadsheet className="h-3 w-3" />
            {view.context}
          </div>
        ) : null}
      </div>
    );
  }

  if (view.kind === "table") {
    return <ResultTable columns={view.columns} rows={view.rows} failed={failed} />;
  }

  return null;
}
