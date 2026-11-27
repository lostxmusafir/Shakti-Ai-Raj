"use client";

import { useCallback, useEffect, useRef, useState, use } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { api, ApiError, User, ChatSession, ChatMessage, StoredFile, PendingInterruptPayload } from "@/lib/api";
import { classifyPollStatus, resolveInterruptOutcome, shouldRetryPoll } from "@/lib/interrupt";
import Sidebar from "@/components/Sidebar";
import AssistantThread from "@/components/AssistantThread";
import { cn } from "@/lib/cn";

const QUICK_ACTIONS = [
  {
    label: "Analyze dataset",
    prompt: "Give me an overview of this dataset: row count, columns and the key totals.",
  },
  {
    label: "Compare files",
    prompt: "Compare Sheet1 and Sheet2 in this workbook and list the differences.",
  },
  {
    label: "Find anomalies",
    prompt: "Find unusual values or anomalies in this dataset.",
  },
  {
    label: "Check policy",
    prompt: "Check this dataset against our security policy and list any violations.",
  },
  {
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
  const [aiTier, setAiTier] = useState<"low" | "pro">("low");
  const [activeAnalysisId, setActiveAnalysisId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("");
  const [pendingInterrupt, setPendingInterrupt] = useState<PendingInterruptPayload | null>(null);
  const [interruptSubmitting, setInterruptSubmitting] = useState(false);
  const [resolvedInterruptLabel, setResolvedInterruptLabel] = useState<string | null>(null);
  const [interruptCancelled, setInterruptCancelled] = useState(false);
  const [streamText, setStreamText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const restoredInterruptIdRef = useRef<string | null>(null);
  const resumeInFlightRef = useRef(false);
  const cancelInFlightRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      try {
        const [me, chatList, msgList, fileList, pendingState] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.getMessages(chatId),
          api.listFiles(),
          api.getPendingInterrupt(chatId).catch(() => ({ pending: false, analysis_id: null, interrupt: null })),
        ]);
        if (cancelled) return;
        setUser(me);
        setChats(chatList);
        setMessages(msgList);
        setFiles(fileList);
        setSelectedFileIds((current) => (current.length ? current : fileList.slice(0, 1).map((file) => file.id)));
        if (pendingState?.pending && pendingState.analysis_id && pendingState.interrupt) {
          restoredInterruptIdRef.current = pendingState.analysis_id;
          setActiveAnalysisId(pendingState.analysis_id);
          setAnalysisStatus("interrupted");
          setPendingInterrupt(pendingState.interrupt);
          setResolvedInterruptLabel(null);
          setInterruptCancelled(false);
        } else {
          restoredInterruptIdRef.current = null;
        }
      } catch {
        if (cancelled) return;
        router.push("/login");
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    loadData();
    return () => {
      cancelled = true;
    };
  }, [chatId, router]);

  useEffect(() => {
    if (!activeAnalysisId || restoredInterruptIdRef.current === activeAnalysisId) return;

    const eventSource = new EventSource(api.getEventsUrl(activeAnalysisId));
    let closed = false;
    let pollStarted = false;
    let pollFailures = 0;
    const MAX_POLL_FAILURES = 4;
    let timer: number | null = null;

    const stopPolling = () => {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    };

    const refresh = () => {
      api.getMessages(chatId).then(setMessages).catch(() => undefined);
    };

    eventSource.addEventListener("analysis.status", (event: MessageEvent) => {
      if (closed) return;
      try {
        setAnalysisStatus(JSON.parse(event.data).status);
      } catch {
        /* ignore malformed frame */
      }
    });

    eventSource.addEventListener("assistant.delta", (event: MessageEvent) => {
      if (closed) return;
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
      closed = true;
      stopPolling();
      setStreamText(null);
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
      closed = true;
      stopPolling();
      setStreamText(null);
      setAnalysisStatus("cancelled");
      setInterruptCancelled(true);
      setActiveAnalysisId(null);
      eventSource.close();
    });

    eventSource.addEventListener("analysis.completed", () => {
      closed = true;
      stopPolling();
      setAnalysisStatus("completed");
      setStreamText(null);
      setPendingInterrupt(null);
      setResolvedInterruptLabel(null);
      setActiveAnalysisId(null);
      refresh();
      eventSource.close();
    });

    eventSource.addEventListener("analysis.failed", (event: MessageEvent) => {
      closed = true;
      stopPolling();
      setAnalysisStatus("failed");
      setStreamText(null);
      setPendingInterrupt(null);
      setResolvedInterruptLabel(null);
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

    const poll = async () => {
      if (closed) return;
      try {
        const analysis = await api.getAnalysis(activeAnalysisId);
        if (closed) return;
        pollFailures = 0;
        setAnalysisStatus(analysis.status);
        const pollKind = classifyPollStatus(analysis.status);
        if (pollKind === "interrupted") {
          closed = true;
          stopPolling();
          setStreamText(null);
          setPendingInterrupt(analysis.pending_interrupt ?? null);
          setResolvedInterruptLabel(null);
          setInterruptCancelled(false);
          return;
        }
        if (pollKind === "cancelled") {
          closed = true;
          stopPolling();
          setStreamText(null);
          setInterruptCancelled(true);
          setActiveAnalysisId(null);
          return;
        }
        if (pollKind === "completed") {
          closed = true;
          stopPolling();
          setStreamText(null);
          setPendingInterrupt(null);
          setResolvedInterruptLabel(null);
          setActiveAnalysisId(null);
          refresh();
          return;
        }
        if (pollKind === "failed") {
          closed = true;
          stopPolling();
          setStreamText(null);
          setPendingInterrupt(null);
          setResolvedInterruptLabel(null);
          setActiveAnalysisId(null);
          setError("The analysis could not be completed. Your question was kept in the thread.");
          refresh();
          return;
        }
        if (!closed) {
          timer = window.setTimeout(poll, 1500);
        }
      } catch (err) {
        if (closed) return;
        const statusCode = err instanceof ApiError ? err.status : null;
        if (shouldRetryPoll(statusCode, pollFailures, MAX_POLL_FAILURES)) {
          pollFailures += 1;
          timer = window.setTimeout(poll, 1500);
          return;
        }
        closed = true;
        stopPolling();
        setStreamText(null);
        setPendingInterrupt(null);
        setResolvedInterruptLabel(null);
        setActiveAnalysisId(null);
        setAnalysisStatus("failed");
        setError(
          err instanceof Error && err.message
            ? err.message
            : "Lost connection while checking analysis status.",
        );
      }
    };

    eventSource.onerror = () => {
      if (closed || pollStarted) return;
      pollStarted = true;
      eventSource.close();
      timer = window.setTimeout(poll, 1500);
    };

    return () => {
      closed = true;
      stopPolling();
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
      restoredInterruptIdRef.current = null;
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
        const response = await api.sendMessage(chatId, content, fileIds, aiTier);
        if (response.analysis_id) {
          restoredInterruptIdRef.current = null;
          setActiveAnalysisId(response.analysis_id);
        }
      } catch (err) {
        setAnalysisStatus("");
        setError(err instanceof Error ? err.message : "Failed to send message.");
      }
    },
    [chatId, aiTier],
  );

  const handleNewChat = async () => {
    try {
      const session = await api.createChat("New Analysis");
      router.push(`/chat/${session.id}`);
    } catch {
      setError("Could not start a new chat.");
    }
  };

  const handleResumeInterrupt = useCallback(
    async (response: string) => {
      if (!activeAnalysisId || !pendingInterrupt || resumeInFlightRef.current || cancelInFlightRef.current) {
        return;
      }
      resumeInFlightRef.current = true;
      setInterruptSubmitting(true);
      setError(null);
      try {
        const res = await api.resumeAnalysis(activeAnalysisId, pendingInterrupt.interrupt_id, response);
        const outcome = resolveInterruptOutcome(res);
        if (outcome.kind === "next_interrupt") {
          setPendingInterrupt(outcome.interrupt);
          setResolvedInterruptLabel(null);
          setAnalysisStatus("interrupted");
        } else if (outcome.kind === "keep_interrupt") {
          setResolvedInterruptLabel(null);
          setAnalysisStatus("interrupted");
        } else if (outcome.kind === "cancelled") {
          setStreamText(null);
          setResolvedInterruptLabel(null);
          setInterruptCancelled(true);
          setActiveAnalysisId(null);
          setAnalysisStatus("cancelled");
        } else if (outcome.kind === "failed") {
          setStreamText(null);
          setPendingInterrupt(null);
          setResolvedInterruptLabel(null);
          setActiveAnalysisId(null);
          setAnalysisStatus("failed");
          setError(res.error || "The analysis could not be completed. Your question was kept in the thread.");
        } else {
          setStreamText(null);
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
        if (err instanceof ApiError && err.status === 409) {
          try {
            const pendingState = await api.getPendingInterrupt(chatId);
            if (pendingState?.pending && pendingState.analysis_id && pendingState.interrupt) {
              restoredInterruptIdRef.current = pendingState.analysis_id;
              setActiveAnalysisId(pendingState.analysis_id);
              setPendingInterrupt(pendingState.interrupt);
              setAnalysisStatus("interrupted");
              setInterruptCancelled(false);
            } else {
              setPendingInterrupt(null);
              setActiveAnalysisId(null);
              setAnalysisStatus("");
              const updatedMsgs = await api.getMessages(chatId);
              setMessages(updatedMsgs);
            }
          } catch {
            /* preserve error banner if resync fails */
          }
        }
      } finally {
        resumeInFlightRef.current = false;
        setInterruptSubmitting(false);
      }
    },
    [activeAnalysisId, pendingInterrupt, chatId],
  );

  const handleCancelInterrupt = useCallback(async () => {
    if (!activeAnalysisId || resumeInFlightRef.current || cancelInFlightRef.current) return;
    cancelInFlightRef.current = true;
    setInterruptSubmitting(true);
    try {
      await api.cancelAnalysis(activeAnalysisId);
      setStreamText(null);
      setResolvedInterruptLabel(null);
      setInterruptCancelled(true);
      setActiveAnalysisId(null);
      setAnalysisStatus("cancelled");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to cancel analysis.");
    } finally {
      cancelInFlightRef.current = false;
      setInterruptSubmitting(false);
    }
  }, [activeAnalysisId]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[var(--background)]">
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

  const busy = Boolean(activeAnalysisId);
  const hasFiles = files.length > 0;

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
      <div className="app-main flex h-screen min-h-0">
      <Sidebar user={user} chats={chats} activeChatId={chatId} onNewChat={handleNewChat} />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="app-header flex h-[68px] shrink-0 items-center justify-between border-b px-5 sm:px-8">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-slate-100">
              {currentChat?.title || "Data Analysis Session"}
            </h1>
            <p className="truncate text-xs text-slate-500">Ask, inspect, and verify your data</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-400" aria-live="polite">
            <span className={cn("h-1.5 w-1.5 rounded-full", hasFiles ? "bg-emerald-400" : "bg-slate-600")} />
            {hasFiles ? `${files.length} dataset${files.length > 1 ? "s" : ""} ready` : "No datasets yet"}
          </div>
        </header>

        <AssistantThread
          userName={user?.name}
          messages={messages}
          files={files}
          knownFiles={knownFiles}
          selectedFileIds={selectedFileIds}
          onSelectFileIds={setSelectedFileIds}
          aiTier={aiTier}
          onChangeAiTier={setAiTier}
          onSend={handleSendMessage}
          busy={busy}
          streamText={streamText}
          analysisStatus={analysisStatus}
          suggestions={QUICK_ACTIONS}
          pendingInterrupt={pendingInterrupt}
          interruptSubmitting={interruptSubmitting}
          resolvedInterruptLabel={resolvedInterruptLabel}
          interruptCancelled={interruptCancelled}
          onResumeInterrupt={handleResumeInterrupt}
          onCancelInterrupt={handleCancelInterrupt}
          errorBanner={errorBanner}
        />
      </main>
    </div>
  );
}
