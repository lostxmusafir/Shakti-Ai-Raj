"use client";

import { useCallback, useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { api, User, ChatSession, ChatMessage, StoredFile, PendingInterruptPayload } from "@/lib/api";
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
        const response = await api.sendMessage(chatId, content, fileIds, aiTier);
        if (response.analysis_id) setActiveAnalysisId(response.analysis_id);
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
      <div className="app-main flex h-screen">
      <Sidebar user={user} chats={chats} activeChatId={chatId} onNewChat={handleNewChat} />

      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-[72px] shrink-0 items-center justify-between border-b border-white/[0.08] px-5 sm:px-8">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-slate-100">
              {currentChat?.title || "Data Analysis Session"}
            </h1>
            <p className="truncate text-xs text-slate-500">Verified analysis workspace · policy-aware results</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className={cn("h-2 w-2 rounded-full", hasFiles ? "bg-emerald-400" : "bg-slate-600")} />
            {hasFiles ? `${files.length} dataset${files.length > 1 ? "s" : ""}` : "No datasets"}
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
