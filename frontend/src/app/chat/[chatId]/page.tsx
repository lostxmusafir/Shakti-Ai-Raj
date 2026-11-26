"use client";

import { useCallback, useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertCircle, ArrowUpRight, Database, GitCompareArrows, ScanSearch, ShieldCheck, Sparkles, Table2 } from "lucide-react";
import { api, User, ChatSession, ChatMessage, StoredFile, PendingInterruptPayload } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import AssistantThread from "@/components/AssistantThread";
import { cn } from "@/lib/cn";

const QUICK_ACTIONS = [
  {
    icon: Database,
    label: "Analyze dataset",
    prompt: "Give me an overview of this dataset: row count, columns and the key totals.",
  },
  {
    icon: GitCompareArrows,
    label: "Compare files",
    prompt: "Compare Sheet1 and Sheet2 in this workbook and list the differences.",
  },
  {
    icon: ScanSearch,
    label: "Find anomalies",
    prompt: "Find unusual values or anomalies in this dataset.",
  },
  {
    icon: ShieldCheck,
    label: "Check policy",
    prompt: "Check this dataset against our security policy and list any violations.",
  },
  {
    icon: Table2,
    label: "Summarize workbook",
    prompt: "Summarize this workbook: sheets, columns, missing values and the main totals.",
  },
];

export default function ChatDetailPage({ params }: { params: Promise<{ chatId: string }> }) {
  const router = useRouter();
  const { chatId } = use(params);

  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [activeAnalysisId, setActiveAnalysisId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("");
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterruptPayload | null>(null);
  const [interruptSubmitting, setInterruptSubmitting] = useState(false);
  const [resolvedInterruptLabel, setResolvedInterruptLabel] = useState<string | null>(null);
  const [interruptCancelled, setInterruptCancelled] = useState(false);
  const [streamText, setStreamText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [me, chatList, msgList, fileList, pendingState] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.getMessages(chatId),
          api.listFiles(),
          api.getPendingInterrupt(chatId).catch(() => ({ pending: false, analysis_id: null, interrupt: null })),
        ]);
        setUser(me);
        setChats(chatList);
        setMessages(msgList);
        setFiles(fileList);
        setSelectedFileIds((current) => (current.length ? current : fileList.slice(0, 1).map((file) => file.id)));
        if (pendingState?.pending && pendingState.analysis_id && pendingState.interrupt) {
          setActiveAnalysisId(pendingState.analysis_id);
          setAnalysisStatus("interrupted");
          setPendingInterrupt(pendingState.interrupt);
          setResolvedInterruptLabel(null);
          setInterruptCancelled(false);
        }
      } catch {
        router.push("/login");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [chatId, router]);

  useEffect(() => {
    if (!activeAnalysisId) return;

    const eventSource = new EventSource(api.getEventsUrl(activeAnalysisId));
    let settled = false;

    const refresh = () => {
      api.getMessages(chatId).then(setMessages).catch(() => undefined);
    };

    eventSource.addEventListener("analysis.status", (event: MessageEvent) => {
      try {
        setAnalysisStatus(JSON.parse(event.data).status);
      } catch {
        /* ignore malformed frame */
      }
    });

    eventSource.addEventListener("assistant.delta", (event: MessageEvent) => {
      try {
        const delta = JSON.parse(event.data).delta;
        if (typeof delta === "string" && delta) {
          setStreamText((previous) => (previous ?? "") + delta);
        }
      } catch {
        /* ignore malformed frame */
      }
    });

    eventSource.addEventListener("analysis.interrupted", (event: MessageEvent) => {
      settled = true;
      try {
        const data = JSON.parse(event.data);
        setAnalysisStatus("interrupted");
        setPendingInterrupt(data.interrupt || null);
        setResolvedInterruptLabel(null);
        setInterruptCancelled(false);
      } catch {
        /* ignore malformed frame */
      }
      eventSource.close();
    });

    eventSource.addEventListener("analysis.cancelled", () => {
      settled = true;
      setAnalysisStatus("cancelled");
      setInterruptCancelled(true);
      setActiveAnalysisId(null);
      eventSource.close();
    });

    eventSource.addEventListener("analysis.completed", () => {
      settled = true;
      setAnalysisStatus("completed");
      setStreamText(null);
      setPendingInterrupt(null);
      setResolvedInterruptLabel(null);
      setActiveAnalysisId(null);
      refresh();
      eventSource.close();
    });

    eventSource.addEventListener("analysis.failed", (event: MessageEvent) => {
      settled = true;
      setAnalysisStatus("failed");
      setStreamText(null);
      setActiveAnalysisId(null);
      setError("The analysis could not be completed. Your question was kept in the thread.");
      eventSource.close();
      try {
        const detail = JSON.parse(event.data)?.error;
        if (typeof detail === "string" && detail) setError(detail);
      } catch {
        /* ignore */
      }
    });

    eventSource.onerror = () => {
      if (settled) return;
      eventSource.close();
      const timer = window.setInterval(async () => {
        try {
          const analysis = await api.getAnalysis(activeAnalysisId);
          setAnalysisStatus(analysis.status);
          if (analysis.status === "completed" || analysis.status === "failed") {
            window.clearInterval(timer);
            setStreamText(null);
            setActiveAnalysisId(null);
            if (analysis.status === "failed") {
              setError("The analysis could not be completed. Your question was kept in the thread.");
            }
            refresh();
          }
        } catch {
          window.clearInterval(timer);
        }
      }, 1500);
    };

    return () => {
      settled = true;
      eventSource.close();
    };
  }, [activeAnalysisId, chatId]);

  const handleSendMessage = useCallback(
    async (content: string, fileIds: string[]) => {
      setError(null);
      setStreamText(null);
      setPendingInterrupt(null);
      setResolvedInterruptLabel(null);
      setInterruptCancelled(false);
      const optimistic: ChatMessage = {
        id: `opt_${Date.now()}`,
        chat_id: chatId,
        role: "user",
        content,
        attachments: fileIds,
        created_at: new Date().toISOString(),
      };
      setMessages((previous) => [...previous, optimistic]);
      setAnalysisStatus("queued");

      try {
        const response = await api.sendMessage(chatId, content, fileIds);
        if (response.analysis_id) setActiveAnalysisId(response.analysis_id);
      } catch (err) {
        setAnalysisStatus("");
        setError(err instanceof Error ? err.message : "Failed to send message.");
      }
    },
    [chatId],
  );

  const handleNewChat = async () => {
    try {
      const session = await api.createChat("New Analysis");
      router.push(`/chat/${session.id}`);
    } catch {
      setError("Could not start a new chat.");
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-700 border-t-slate-300" />
      </div>
    );
  }

  const currentChat = chats.find((chat) => chat.id === chatId);
  const knownFiles = files.map((file) => ({
    id: file.id,
    original_name: file.original_name,
    row_count: file.schema_profile?.row_count ?? null,
  }));

  const handleResumeInterrupt = useCallback(
    async (response: string) => {
      if (!activeAnalysisId || !pendingInterrupt) return;
      setInterruptSubmitting(true);
      setError(null);
      const matchedOpt = pendingInterrupt.options?.find((o) => o.id === response);
      setResolvedInterruptLabel(matchedOpt?.label || response);
      try {
        const res = await api.resumeAnalysis(activeAnalysisId, pendingInterrupt.interrupt_id, response);
        if (res.status === "interrupted" && res.interrupt) {
          setPendingInterrupt(res.interrupt);
          setResolvedInterruptLabel(null);
          setAnalysisStatus("interrupted");
        } else if (res.status === "cancelled") {
          setInterruptCancelled(true);
          setActiveAnalysisId(null);
        } else {
          setPendingInterrupt(null);
          setResolvedInterruptLabel(null);
          setActiveAnalysisId(null);
          setAnalysisStatus("completed");
          const updatedMsgs = await api.getMessages(chatId);
          setMessages(updatedMsgs);
        }
      } catch (err) {
        setResolvedInterruptLabel(null);
        setError(err instanceof Error ? err.message : "Failed to resume analysis.");
      } finally {
        setInterruptSubmitting(false);
      }
    },
    [activeAnalysisId, pendingInterrupt, chatId],
  );

  const handleCancelInterrupt = useCallback(async () => {
    if (!activeAnalysisId) return;
    setInterruptSubmitting(true);
    try {
      await api.cancelAnalysis(activeAnalysisId);
      setInterruptCancelled(true);
      setActiveAnalysisId(null);
      setAnalysisStatus("cancelled");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel analysis.");
    } finally {
      setInterruptSubmitting(false);
    }
  }, [activeAnalysisId]);

  const busy = Boolean(activeAnalysisId);
  const hasFiles = files.length > 0;

  const emptyState = (
    <div className="flex flex-1 items-center justify-center py-10">
      <div className="w-full max-w-xl">
        <div className="mb-6 text-center">
          <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-300 ring-1 ring-inset ring-indigo-400/20">
            <Sparkles className="h-5 w-5" />
          </div>
          <h2 className="mt-3 text-[17px] font-semibold tracking-tight text-white">
            What would you like to analyze?
          </h2>
          <p className="mx-auto mt-1 max-w-sm text-[12.5px] leading-6 text-slate-400">
            Ask in English or Hinglish. Queries run through DuckDB and every answer is verified against your
            policy rules.
          </p>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.label}
                type="button"
                disabled={!hasFiles}
                onClick={() => handleSendMessage(action.prompt, selectedFileIds)}
                className={cn(
                  "group flex items-start gap-2.5 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2.5 text-left transition",
                  hasFiles
                    ? "hover:border-slate-700 hover:bg-slate-900/80"
                    : "cursor-not-allowed opacity-50",
                )}
              >
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500 group-hover:text-indigo-300" />
                <span className="text-[12px] leading-5 text-slate-300">
                  <span className="block font-medium text-slate-200">{action.label}</span>
                  <span className="text-[11px] text-slate-500">{action.prompt}</span>
                </span>
              </button>
            );
          })}
        </div>

        {!hasFiles ? (
          <p className="mt-4 text-center text-[11.5px] text-slate-500">
            Upload a dataset first —{" "}
            <Link href="/files" className="inline-flex items-center gap-0.5 text-indigo-300 hover:text-indigo-200">
              open Datasets <ArrowUpRight className="h-3 w-3" />
            </Link>
          </p>
        ) : null}
      </div>
    </div>
  );

  const errorBanner = error ? (
    <div className="flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-500/[0.06] px-3 py-2 text-[12px] text-red-200">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-400" />
      <div>
        <div className="font-medium">Something went wrong</div>
        <div className="mt-0.5 text-red-200/70">{error}</div>
      </div>
    </div>
  ) : null;

  return (
    <div className="flex h-screen bg-slate-950">
      <Sidebar user={user} chats={chats} activeChatId={chatId} onNewChat={handleNewChat} />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800/80 px-5 sm:px-6">
          <div className="min-w-0">
            <h1 className="truncate text-[13px] font-medium text-slate-100">
              {currentChat?.title || "Data Analysis Session"}
            </h1>
            <p className="truncate text-[11px] text-slate-500">Deterministic query engine · policy verification</p>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <span className={cn("h-1.5 w-1.5 rounded-full", hasFiles ? "bg-emerald-500" : "bg-slate-600")} />
            {hasFiles ? `${files.length} dataset${files.length > 1 ? "s" : ""}` : "No datasets"}
          </div>
        </header>

        <AssistantThread
          messages={messages}
          files={files}
          knownFiles={knownFiles}
          selectedFileIds={selectedFileIds}
          onSelectFileIds={setSelectedFileIds}
          onSend={handleSendMessage}
          busy={busy}
          streamText={streamText}
          analysisStatus={analysisStatus}
          pendingInterrupt={pendingInterrupt}
          interruptSubmitting={interruptSubmitting}
          resolvedInterruptLabel={resolvedInterruptLabel}
          interruptCancelled={interruptCancelled}
          onResumeInterrupt={handleResumeInterrupt}
          onCancelInterrupt={handleCancelInterrupt}
          emptyState={emptyState}
          errorBanner={errorBanner}
        />
      </main>
    </div>
  );
}
