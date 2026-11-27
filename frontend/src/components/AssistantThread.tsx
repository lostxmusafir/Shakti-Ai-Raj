"use client";

import { useMemo, useState, type ReactNode } from "react";
import {
  ActionBarPrimitive,
  AssistantRuntimeProvider,
  AuiIf,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  CopyIcon,
  DatabaseIcon,
  PlusIcon,
  SquareIcon,
  XIcon,
} from "lucide-react";
import Link from "next/link";
import type { ChatMessage, PendingInterruptPayload, StoredFile } from "@/lib/api";
import AnswerBody, { type KnownFile } from "@/components/AnswerBody";
import AnalysisStatusIndicator from "@/components/AnalysisStatusIndicator";
import InterruptCard from "@/components/InterruptCard";
import Attachments from "@/components/ai-elements/Attachments";
import { cn } from "@/lib/cn";

export interface SuggestionItem {
  label: string;
  prompt: string;
}

interface AssistantThreadProps {
  userName?: string | null;
  messages: ChatMessage[];
  files: StoredFile[];
  knownFiles: KnownFile[];
  selectedFileIds: string[];
  onSelectFileIds: (ids: string[]) => void;
  aiTier?: "low" | "pro";
  onChangeAiTier?: (tier: "low" | "pro") => void;
  onSend: (content: string, fileIds: string[]) => Promise<void>;
  busy: boolean;
  streamText: string | null;
  analysisStatus: string;
  suggestions?: SuggestionItem[];
  pendingInterrupt?: PendingInterruptPayload | null;
  interruptSubmitting?: boolean;
  resolvedInterruptLabel?: string | null;
  interruptCancelled?: boolean;
  onResumeInterrupt?: (response: string) => Promise<void>;
  onCancelInterrupt?: () => Promise<void>;
  errorBanner: ReactNode;
}

function toThreadMessage(message: ChatMessage): ThreadMessageLike {
  return {
    id: message.id,
    role: message.role === "user" ? "user" : "assistant",
    content: [{ type: "text", text: message.content || "" }],
    createdAt: message.created_at ? new Date(message.created_at) : new Date(),
    metadata: {
      custom: {
        raw: message,
      },
    },
  };
}

function firstName(name?: string | null): string {
  if (!name) return "";
  return name.trim().split(/\s+/)[0] || "";
}

function AuiGreeting({ userName }: { userName?: string | null }) {
  const first = firstName(userName);
  return (
    <div className="thread-greeting mb-8 flex flex-col px-2">
      <p className="text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">
        {first ? `How can I help you, ${first}?` : "How can I help you today?"}
      </p>
      <p className="mt-2 max-w-xl text-sm leading-6 text-slate-400">
        Ask about the selected dataset. Every verified result keeps its evidence and query close by.
      </p>
    </div>
  );
}

function AuiUserMessage({ files }: { files: StoredFile[] }) {
  const raw = useAuiState((s) => s.message.metadata?.custom?.raw as ChatMessage | undefined);
  const textPart = useAuiState((s) => {
    const first = s.message.content.find((p) => p.type === "text");
    return first && "text" in first ? first.text : "";
  });

  const attachmentItems = (raw?.attachments ?? []).map((id) => {
    const file = files.find((item) => item.id === id);
    return {
      id,
      name: file?.original_name || "Dataset",
      rows: file?.schema_profile?.row_count ?? null,
      state: file?.status ?? null,
    };
  });

  return (
    <MessagePrimitive.Root
      data-role="user"
      className="grid auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-y-2 px-2 [&:where(>*)]:col-start-2"
    >
      <div className="relative col-start-2 min-w-0">
        <div className="rounded-[var(--composer-radius)] bg-white/[0.08] px-4 py-2 text-[15px] leading-6 text-slate-100 break-words">
          <div className="whitespace-pre-wrap">{raw?.content ?? textPart}</div>
          {attachmentItems.length ? (
            <Attachments items={attachmentItems} compact className="mt-2 justify-end" />
          ) : null}
        </div>
      </div>
    </MessagePrimitive.Root>
  );
}

function AuiAssistantMessage({ knownFiles }: { knownFiles: KnownFile[] }) {
  const isOptimistic = useAuiState((s) => Boolean(s.message.metadata?.isOptimistic));
  const raw = useAuiState((s) => s.message.metadata?.custom?.raw as ChatMessage | undefined);
  const textPart = useAuiState((s) => {
    const first = s.message.content.find((p) => p.type === "text");
    return first && "text" in first ? first.text : "";
  });

  if (isOptimistic || (!raw && !textPart.trim())) {
    return null;
  }

  return (
    <MessagePrimitive.Root
      data-role="assistant"
      className="assistant-message group relative -mb-7.5 pb-7.5"
    >
      <div className="px-2 text-[15px] leading-7 text-slate-200">
        <AnswerBody
          content={raw?.content ?? textPart}
          result={raw?.metadata?.result}
          verification={raw?.metadata?.verification}
          provenance={raw?.metadata?.provenance}
          files={knownFiles}
        />
      </div>
      <ActionBarPrimitive.Root
        hideWhenRunning
        autohide="not-last"
        className="mt-1 flex min-h-7 items-center gap-1 pl-2 text-slate-500"
      >
        <ActionBarPrimitive.Copy asChild>
          <button
            type="button"
            aria-label="Copy message"
            className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-[12px] transition-colors hover:bg-white/[0.06] hover:text-slate-200"
          >
            <CopyIcon className="size-3.5 group-data-[copied]:hidden" />
            <CheckIcon className="hidden size-3.5 text-emerald-400 group-data-[copied]:block" />
            <span>Copy</span>
          </button>
        </ActionBarPrimitive.Copy>
      </ActionBarPrimitive.Root>
    </MessagePrimitive.Root>
  );
}

export default function AssistantThread({
  userName,
  messages,
  files,
  knownFiles,
  selectedFileIds,
  onSelectFileIds,
  aiTier = "low",
  onChangeAiTier,
  onSend,
  busy,
  streamText,
  analysisStatus,
  suggestions = [],
  pendingInterrupt = null,
  interruptSubmitting = false,
  resolvedInterruptLabel = null,
  interruptCancelled = false,
  onResumeInterrupt,
  onCancelInterrupt,
  errorBanner,
}: AssistantThreadProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const adapter = useMemo(
    () => ({
      messages,
      isRunning: busy,
      convertMessage: toThreadMessage,
      onNew: async (append: AppendMessage) => {
        const text = append.content
          .filter((part): part is { type: "text"; text: string } => part.type === "text")
          .map((part) => part.text)
          .join("\n")
          .trim();
        if (!text || busy) return;
        await onSend(text, selectedFileIds);
      },
    }),
    [messages, busy, onSend, selectedFileIds],
  );

  const runtime = useExternalStoreRuntime(adapter);

  const toggleFile = (id: string) => {
    if (selectedFileIds.includes(id)) {
      onSelectFileIds(selectedFileIds.filter((item) => item !== id));
    } else {
      onSelectFileIds([...selectedFileIds, id]);
    }
  };

  const isEmpty = messages.length === 0 && !busy;

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root
        className="flex min-h-0 flex-1 flex-col bg-[var(--background)] text-slate-100"
        style={{
          ["--thread-max-width" as string]: "44rem",
          ["--composer-bg" as string]: "rgba(255,255,255,0.035)",
          ["--composer-radius" as string]: "1rem",
          ["--composer-padding" as string]: "8px",
        }}
      >
        <ThreadPrimitive.Viewport
          turnAnchor="top"
          className={cn(
            "relative flex flex-1 flex-col overflow-x-hidden overflow-y-scroll scroll-smooth",
          )}
        >
          <div className={cn("mx-auto flex w-full max-w-[var(--thread-max-width)] flex-1 flex-col px-4 pt-4", isEmpty && "justify-center")}>
            {isEmpty ? <AuiGreeting userName={userName} /> : null}

            <div className="mb-14 flex flex-col gap-y-6 empty:hidden">
              <ThreadPrimitive.Messages
                components={{
                  UserMessage: () => <AuiUserMessage files={files} />,
                  AssistantMessage: () => <AuiAssistantMessage knownFiles={knownFiles} />,
                }}
              />

              {pendingInterrupt && onResumeInterrupt ? (
                <div className="w-full">
                  <InterruptCard
                    key={pendingInterrupt.interrupt_id}
                    interrupt={pendingInterrupt}
                    submitting={interruptSubmitting}
                    resolvedLabel={resolvedInterruptLabel}
                    cancelled={interruptCancelled}
                    onSubmit={onResumeInterrupt}
                    onCancel={onCancelInterrupt}
                  />
                </div>
              ) : null}

              {busy && !pendingInterrupt ? (
                <div className="w-full px-2">
                  {streamText ? (
                    <AnswerBody content={streamText} streaming />
                  ) : (
                    <AnalysisStatusIndicator status={analysisStatus || "queued"} />
                  )}
                </div>
              ) : null}

              {errorBanner ? <div className="w-full px-2">{errorBanner}</div> : null}
            </div>

            <ThreadPrimitive.ViewportFooter className={cn("flex flex-col gap-4 overflow-visible bg-[var(--background)] pb-4 md:pb-6", !isEmpty && "sticky bottom-0 mt-auto rounded-t-[var(--composer-radius)]")}>
            <ThreadPrimitive.ScrollToBottom asChild>
              <button
                type="button"
                aria-label="Scroll to bottom"
                className="absolute -top-11 z-10 grid size-8 place-items-center self-center rounded-md border border-white/10 bg-[#17191c] text-slate-300 transition-colors hover:border-white/25 hover:text-white disabled:invisible"
              >
                <ArrowDownIcon className="size-4" />
              </button>
            </ThreadPrimitive.ScrollToBottom>

            {/* Official assistant-ui Composer */}
            <ComposerPrimitive.Root className="relative w-full">
              {pickerOpen && files.length > 0 ? (
                <div className="mb-2 flex flex-wrap items-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/95 p-2.5 shadow-xl">
                  <span className="mr-1 text-[11px] font-medium text-slate-400">Select datasets:</span>
                  {files.map((file) => {
                    const selected = selectedFileIds.includes(file.id);
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => toggleFile(file.id)}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-[11.5px] transition-colors",
                          selected
                            ? "border-white/20 bg-white/[0.10] text-[var(--accent-strong)]"
                            : "border-white/10 bg-white/[0.03] text-slate-400 hover:border-white/25 hover:text-slate-200",
                        )}
                      >
                        <DatabaseIcon className="size-3" />
                        <span className="max-w-[180px] truncate">{file.original_name}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null}

              <div className="thread-composer flex w-full flex-col gap-2 rounded-[var(--composer-radius)] border p-[var(--composer-padding)] transition-colors focus-within:border-white/40">
                {selectedFileIds.length > 0 ? (
                  <div className="flex flex-wrap items-center gap-1.5 px-3 pt-2.5">
                    {selectedFileIds.map((id) => {
                      const f = files.find((item) => item.id === id);
                      if (!f) return null;
                      return (
                        <span
                          key={id}
                          className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.06] px-2 py-0.5 text-[11.5px] text-slate-200"
                        >
                          <DatabaseIcon className="size-3 text-[var(--accent)]" />
                          <span className="max-w-[180px] truncate">{f.original_name}</span>
                          <button
                            type="button"
                            onClick={() => toggleFile(id)}
                            aria-label={`Remove ${f.original_name}`}
                            className="ml-0.5 text-slate-400 hover:text-white"
                          >
                            <XIcon className="size-3" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                ) : null}

                <ComposerPrimitive.Input asChild>
                  <textarea
                    placeholder="Send a message..."
                    disabled={busy}
                    rows={1}
                    className="max-h-48 min-h-10 w-full resize-none bg-transparent px-2.5 py-1 text-base leading-6 text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
                  />
                </ComposerPrimitive.Input>

                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1">
                    {files.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => setPickerOpen((prev) => !prev)}
                        aria-label="Attach dataset"
                        className={cn(
                          "grid size-7 shrink-0 place-items-center rounded-lg transition-colors",
                          pickerOpen
                            ? "bg-white/10 text-white"
                            : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100",
                        )}
                      >
                        <PlusIcon className="size-4" />
                      </button>
                    ) : (
                      <Link
                        href="/files"
                        className="inline-flex h-7 items-center gap-1 rounded-lg px-2 text-[12px] text-slate-400 transition-colors hover:bg-white/[0.06] hover:text-slate-200"
                      >
                        <PlusIcon className="size-3.5" />
                        <span>Upload dataset</span>
                      </Link>
                    )}
                    <div className="inline-flex items-center rounded-md border border-white/10 bg-white/[0.03] p-0.5 text-[11.5px]" aria-label="AI tier">
                      <button
                        type="button"
                        onClick={() => onChangeAiTier?.("low")}
                        title="Mistral 3B (Round-Robin)"
                        className={cn(
                          "rounded-md px-2 py-0.5 font-medium transition-colors",
                          aiTier === "low"
                            ? "bg-white/15 text-white"
                            : "text-slate-400 hover:text-slate-200",
                        )}
                      >
                        AI Low
                      </button>
                      <button
                        type="button"
                        onClick={() => onChangeAiTier?.("pro")}
                        title="Zhipu GLM-4-Flash (Round-Robin)"
                        className={cn(
                          "rounded-md px-2 py-0.5 font-medium transition-colors",
                          aiTier === "pro"
                            ? "bg-white/15 text-white"
                            : "text-slate-400 hover:text-slate-200",
                        )}
                      >
                        AI Pro
                      </button>
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-1">
                    <AuiIf condition={(s) => !s.thread.isRunning}>
                      <ComposerPrimitive.Send asChild>
                        <button
                          type="submit"
                          disabled={busy}
                          aria-label="Send message"
                          className="grid size-7 place-items-center rounded-lg bg-white text-slate-950 transition-opacity hover:bg-slate-200 disabled:opacity-35"
                        >
                          <ArrowUpIcon className="size-4" />
                        </button>
                      </ComposerPrimitive.Send>
                    </AuiIf>
                    {busy && onCancelInterrupt ? (
                      <button
                        type="button"
                        disabled={interruptSubmitting}
                        onClick={() => onCancelInterrupt()}
                        aria-label="Stop"
                        className="grid size-7 place-items-center rounded-lg bg-white text-slate-950 transition-opacity hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <SquareIcon className="size-3 fill-current" />
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </ComposerPrimitive.Root>

            {/* Official assistant-ui Suggestion chips on empty thread */}
            {isEmpty && suggestions.length > 0 ? (
              <div className="flex w-full flex-col">
                {suggestions.map((suggestion) => (
                  <ThreadPrimitive.Suggestion
                    key={suggestion.prompt}
                    prompt={suggestion.prompt}
                    send
                    disabled={files.length === 0}
                    className="group flex w-full items-baseline gap-2.5 rounded-md px-2 py-2 text-left text-sm text-slate-400 transition-colors hover:bg-white/[0.03] hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <span className="text-xs text-[var(--accent)] group-hover:text-white">↳</span>
                    <span className="truncate">{suggestion.label}</span>
                  </ThreadPrimitive.Suggestion>
                ))}
              </div>
            ) : null}
            </ThreadPrimitive.ViewportFooter>
          </div>
        </ThreadPrimitive.Viewport>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}
