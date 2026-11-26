"use client";

import { useMemo, type ReactNode } from "react";
import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useAuiState,
  useExternalStoreRuntime,
  type AppendMessage,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { ArrowDown, ArrowUp, Database, Paperclip, Sparkles, X } from "lucide-react";
import Link from "next/link";
import type { ChatMessage, PendingInterruptPayload, StoredFile } from "@/lib/api";
import AnswerBody, { type KnownFile } from "@/components/AnswerBody";
import AnalysisStatusIndicator from "@/components/AnalysisStatusIndicator";
import InterruptCard from "@/components/InterruptCard";
import Attachments from "@/components/ai-elements/Attachments";
import Message from "@/components/ai-elements/Message";
import { cn } from "@/lib/cn";

interface AssistantThreadProps {
  messages: ChatMessage[];
  files: StoredFile[];
  knownFiles: KnownFile[];
  selectedFileIds: string[];
  onSelectFileIds: (ids: string[]) => void;
  onSend: (content: string, fileIds: string[]) => Promise<void>;
  busy: boolean;
  streamText: string | null;
  analysisStatus: string;
  pendingInterrupt?: PendingInterruptPayload | null;
  interruptSubmitting?: boolean;
  resolvedInterruptLabel?: string | null;
  interruptCancelled?: boolean;
  onResumeInterrupt?: (response: string) => Promise<void>;
  onCancelInterrupt?: () => Promise<void>;
  emptyState: ReactNode;
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

function AssistantUserMessage({
  files,
}: {
  files: StoredFile[];
}) {
  const raw = useAuiState((s) => (s.message.metadata?.custom?.raw as ChatMessage | undefined));
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
    <MessagePrimitive.Root className="w-full">
      <Message role="user">
        <div className="whitespace-pre-wrap">{raw?.content ?? textPart}</div>
        {attachmentItems.length ? (
          <Attachments items={attachmentItems} compact className="mt-2 justify-end" />
        ) : null}
      </Message>
    </MessagePrimitive.Root>
  );
}

function AssistantBotMessage({
  knownFiles,
}: {
  knownFiles: KnownFile[];
}) {
  const raw = useAuiState((s) => (s.message.metadata?.custom?.raw as ChatMessage | undefined));
  const textPart = useAuiState((s) => {
    const first = s.message.content.find((p) => p.type === "text");
    return first && "text" in first ? first.text : "";
  });

  return (
    <MessagePrimitive.Root className="w-full">
      <Message role="assistant">
        <AnswerBody
          content={raw?.content ?? textPart}
          result={raw?.metadata?.result}
          verification={raw?.metadata?.verification}
          provenance={raw?.metadata?.provenance}
          files={knownFiles}
        />
      </Message>
    </MessagePrimitive.Root>
  );
}

export default function AssistantThread({
  messages,
  files,
  knownFiles,
  selectedFileIds,
  onSelectFileIds,
  onSend,
  busy,
  streamText,
  analysisStatus,
  pendingInterrupt = null,
  interruptSubmitting = false,
  resolvedInterruptLabel = null,
  interruptCancelled = false,
  onResumeInterrupt,
  onCancelInterrupt,
  emptyState,
  errorBanner,
}: AssistantThreadProps) {
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

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
        <ThreadPrimitive.Viewport className="relative flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          <div className="mx-auto w-full max-w-3xl space-y-7">
            <ThreadPrimitive.Empty>{!busy ? emptyState : null}</ThreadPrimitive.Empty>

            <ThreadPrimitive.Messages
              components={{
                UserMessage: () => <AssistantUserMessage files={files} />,
                AssistantMessage: () => <AssistantBotMessage knownFiles={knownFiles} />,
              }}
            />

            {pendingInterrupt && onResumeInterrupt ? (
              <Message role="assistant">
                <InterruptCard
                  interrupt={pendingInterrupt}
                  submitting={interruptSubmitting}
                  resolvedLabel={resolvedInterruptLabel}
                  cancelled={interruptCancelled}
                  onSubmit={onResumeInterrupt}
                  onCancel={onCancelInterrupt}
                />
              </Message>
            ) : null}

            {busy && !pendingInterrupt ? (
              <Message role="assistant">
                {streamText ? (
                  <AnswerBody content={streamText} streaming />
                ) : (
                  <AnalysisStatusIndicator status={analysisStatus || "queued"} />
                )}
              </Message>
            ) : null}

            {errorBanner}
          </div>

          <ThreadPrimitive.ScrollToBottom asChild>
            <button
              type="button"
              aria-label="Scroll to bottom"
              className="sticky bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-slate-700/80 bg-slate-900/90 p-2 text-slate-300 shadow-lg backdrop-blur transition hover:bg-slate-800 hover:text-white disabled:pointer-events-none disabled:opacity-0"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
          </ThreadPrimitive.ScrollToBottom>
        </ThreadPrimitive.Viewport>

        {/* assistant-ui Composer */}
        <div className="shrink-0 border-t border-slate-800/80 bg-slate-950/90 px-4 py-3 sm:px-6">
          <div className="mx-auto w-full max-w-3xl space-y-2">
            {files.length > 0 ? (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="inline-flex items-center gap-1 text-[11px] text-slate-500">
                  <Database className="h-3 w-3" />
                  Datasets:
                </span>
                {files.map((file) => {
                  const selected = selectedFileIds.includes(file.id);
                  return (
                    <button
                      key={file.id}
                      type="button"
                      onClick={() => toggleFile(file.id)}
                      className={cn(
                        "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] transition",
                        selected
                          ? "border-indigo-500/40 bg-indigo-500/15 text-indigo-200"
                          : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200",
                      )}
                    >
                      <Paperclip className="h-2.5 w-2.5" />
                      <span className="max-w-[160px] truncate">{file.original_name}</span>
                      {selected ? <X className="h-2.5 w-2.5 opacity-70" /> : null}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="flex items-center justify-between text-[11px] text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <Sparkles className="h-3 w-3 text-indigo-400" />
                  No dataset attached — general assistant mode
                </span>
                <Link href="/files" className="text-indigo-300 hover:text-indigo-200">
                  Upload dataset
                </Link>
              </div>
            )}

            <ComposerPrimitive.Root className="flex items-end gap-2 rounded-2xl border border-slate-800 bg-slate-900/80 px-3 py-2 focus-within:border-indigo-500/50">
              <ComposerPrimitive.Input
                placeholder="Ask a question about your data in English or Hinglish..."
                disabled={busy}
                rows={1}
                className="max-h-40 min-h-[36px] flex-1 resize-none bg-transparent py-1.5 text-[13px] text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
              />
              <ComposerPrimitive.Send asChild>
                <button
                  type="submit"
                  disabled={busy}
                  aria-label="Send message"
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ArrowUp className="h-4 w-4" />
                </button>
              </ComposerPrimitive.Send>
            </ComposerPrimitive.Root>
          </div>
        </div>
      </ThreadPrimitive.Root>
    </AssistantRuntimeProvider>
  );
}
