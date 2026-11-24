"use client";

import { useEffect, useState, useRef, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  User,
  ChatSession,
  ChatMessage,
  StoredFile,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import Composer from "@/components/Composer";
import AnalysisStatusIndicator from "@/components/AnalysisStatusIndicator";
import ResultTable from "@/components/ResultTable";
import SourceEvidenceCard from "@/components/SourceEvidenceCard";
import MarkdownMessage from "@/components/MarkdownMessage";
import WelcomePanel from "@/components/WelcomePanel";
import { Layers, User as UserIcon, FileSpreadsheet } from "lucide-react";

export default function ChatDetailPage({ params }: { params: Promise<{ chatId: string }> }) {
  const { chatId } = use(params);
  return <ChatWorkspace key={chatId} chatId={chatId} />;
}

function ChatWorkspace({ chatId }: { chatId: string }) {
  const router = useRouter();

  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [activeAnalysisId, setActiveAnalysisId] = useState<string | null>(null);
  const [analysisStatus, setAnalysisStatus] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<EventSource | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const currentChatRef = useRef(chatId);

  const stopActiveWork = useCallback((clearState = true) => {
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    streamRef.current?.close();
    streamRef.current = null;
    if (pollingTimerRef.current) {
      clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    if (clearState) {
      setActiveAnalysisId(null);
      setAnalysisStatus("");
    }
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, analysisStatus]);

  const handleSendMessage = useCallback(async (content: string, fileIds: string[]) => {
    const controller = new AbortController();
    requestControllerRef.current = controller;
    const requestChatId = chatId;
    try {
      const optMsg: ChatMessage = {
        id: `opt_${Date.now()}`,
        chat_id: chatId,
        role: "user",
        content,
        attachments: fileIds,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optMsg]);
      setAnalysisStatus("queued");

      const resp = await api.sendMessage(chatId, content, fileIds, controller.signal);
      if (currentChatRef.current !== requestChatId) return;
      if (resp.analysis_id) {
        setActiveAnalysisId(resp.analysis_id);
      }
    } catch (err: any) {
      if (err?.name !== "AbortError" && currentChatRef.current === requestChatId) {
        alert(err.message || "Failed to send query.");
        setAnalysisStatus("");
      }
    } finally {
      if (requestControllerRef.current === controller) requestControllerRef.current = null;
    }
  }, [chatId]);

  // Load initial session data
  useEffect(() => {
    let cancelled = false;
    async function loadData() {
      try {
        const [me, chatList, msgList, fileList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.getMessages(chatId),
          api.listFiles(),
        ]);
        if (cancelled || currentChatRef.current !== chatId) return;
        setUser(me);
        setChats(chatList);
        setMessages(msgList);
        setFiles(fileList);

        // Check if there was a pending prompt queued from the home page
        if (typeof window !== "undefined") {
          const pendingKey = `pending_prompt_${chatId}`;
          const pending = sessionStorage.getItem(pendingKey);
          if (pending) {
            sessionStorage.removeItem(pendingKey);
            try {
              const { content, fileIds } = JSON.parse(pending);
              if (content) {
                setTimeout(() => {
                  handleSendMessage(content, fileIds || []);
                }, 50);
              }
            } catch {}
          }
        }
      } catch (err) {
        if (!cancelled) router.push("/login");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadData();
    return () => {
      cancelled = true;
      stopActiveWork(false);
    };
  }, [chatId, router, handleSendMessage, stopActiveWork]);

  // SSE stream listener
  useEffect(() => {
    if (!activeAnalysisId) return;

    let cancelled = false;
    const analysisId = activeAnalysisId;
    const eventSource = new EventSource(api.getEventsUrl(analysisId), { withCredentials: true });
    streamRef.current = eventSource;
    const isCurrent = () => !cancelled && currentChatRef.current === chatId;
    const isChatCurrent = () => currentChatRef.current === chatId;

    eventSource.addEventListener("analysis.status", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        if (isCurrent()) setAnalysisStatus(data.status);
      } catch {}
    });

    eventSource.addEventListener("analysis.completed", (e: any) => {
      try {
        if (!isCurrent()) return;
        setAnalysisStatus("completed");
        api.getMessages(chatId).then((nextMessages) => {
          if (isChatCurrent()) setMessages(nextMessages);
        });
      } catch {}
      if (!isCurrent()) return;
      eventSource.close();
      setActiveAnalysisId(null);
    });

    eventSource.addEventListener("analysis.failed", (e: any) => {
      if (!isCurrent()) return;
      setAnalysisStatus("failed");
      eventSource.close();
      setActiveAnalysisId(null);
    });

    eventSource.onerror = () => {
      if (!isCurrent() || pollingTimerRef.current) return;
      pollingTimerRef.current = setInterval(async () => {
        if (!isCurrent()) return;
        try {
          const ana = await api.getAnalysis(analysisId);
          if (ana.status === "completed" || ana.status === "failed") {
            setAnalysisStatus(ana.status);
            if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
            pollingTimerRef.current = null;
            setActiveAnalysisId(null);
            api.getMessages(chatId).then((nextMessages) => {
              if (isChatCurrent()) setMessages(nextMessages);
            });
          } else {
            setAnalysisStatus(ana.status);
          }
        } catch {
          if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
          pollingTimerRef.current = null;
        }
      }, 1000);
      eventSource.close();
    };

    return () => {
      cancelled = true;
      eventSource.close();
      if (pollingTimerRef.current) {
        clearInterval(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, [activeAnalysisId, chatId]);

  const handleNewChat = () => {
    stopActiveWork();
    router.push("/chat");
  };

  const handleDeleteChat = async (deletedChatId: string) => {
    const wasActive = deletedChatId === chatId;
    if (wasActive) stopActiveWork();
    try {
      await api.deleteChat(deletedChatId);
      setChats((prev) => prev.filter((chat) => chat.id !== deletedChatId));
      if (wasActive) {
        router.replace("/chat");
      }
    } catch (err: any) {
      alert(err.message || "Failed to delete session.");
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-synapse-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 rounded-full border-2 border-synapse-border border-t-synapse-accent animate-spin" />
          <p className="text-xs text-synapse-muted">Loading workspace...</p>
        </div>
      </div>
    );
  }

  const currentChat = chats.find((c) => c.id === chatId);

  return (
    <div className="flex h-screen bg-synapse-bg text-synapse-text overflow-hidden">
      <Sidebar
        user={user}
        chats={chats}
        activeChatId={chatId}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
      />

      <main className="flex flex-1 flex-col overflow-hidden relative pt-14 lg:pt-0">
        {/* Workspace Top Header */}
        <header className="hidden lg:flex h-14 shrink-0 items-center justify-between border-b border-synapse-border bg-synapse-surface/60 px-6 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            <h1 className="text-xs font-semibold text-synapse-text truncate max-w-sm">
              {currentChat?.title || "Analytical Session"}
            </h1>
            <span className="text-[11px] text-synapse-muted hidden md:inline">
              Deterministic Query Engine • Policy Verification
            </span>
          </div>

          <div className="flex items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-synapse-border bg-synapse-raised px-2.5 py-0.5 text-[11px] text-synapse-secondary">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              DuckDB Active
            </span>
          </div>
        </header>

        {/* Message View Area */}
        <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-6 space-y-6">
          {messages.length === 0 ? (
            <WelcomePanel
              user={user}
              recentChats={chats.filter((c) => c.id !== chatId)}
              onSelectPrompt={(prompt) => handleSendMessage(prompt, selectedFileIds)}
              onOpenChat={(id) => router.push(`/chat/${id}`)}
            />
          ) : (
            <div className="max-w-4xl mx-auto space-y-6">
              {messages.map((msg) => {
                const isUser = msg.role === "user";
                const resultData = msg.metadata?.result;

                return (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${isUser ? "items-end" : "items-start"} space-y-2 animate-in fade-in duration-150`}
                  >
                    {/* Message Bubble Container */}
                    <div
                      className={`flex gap-3 max-w-3xl ${
                        isUser ? "flex-row-reverse" : "flex-row w-full"
                      }`}
                    >
                      {/* Avatar */}
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-synapse-border bg-synapse-raised text-synapse-text shadow-subtle">
                        {isUser ? (
                          <UserIcon className="h-3.5 w-3.5 text-synapse-secondary" />
                        ) : (
                          <Layers className="h-3.5 w-3.5 text-synapse-accent" />
                        )}
                      </div>

                      {/* Content Block */}
                      <div
                        className={`rounded-2xl px-4 py-3 text-xs sm:text-sm leading-relaxed ${
                          isUser
                            ? "bg-synapse-raised border border-synapse-border-strong text-synapse-text shadow-subtle max-w-xl"
                            : "w-full border border-synapse-border/80 bg-synapse-surface/90 text-synapse-text shadow-card"
                        }`}
                      >
                        {/* Attachments Pills on User message */}
                        {isUser && msg.attachments && msg.attachments.length > 0 && (
                          <div className="mb-2 flex flex-wrap gap-1.5 pb-2 border-b border-synapse-border">
                            {msg.attachments.map((fid) => {
                              const f = files.find((file) => file.id === fid);
                              return (
                                <span
                                  key={fid}
                                  className="inline-flex items-center gap-1 rounded bg-synapse-surface border border-synapse-border px-2 py-0.5 text-[10px] text-synapse-secondary"
                                >
                                  <FileSpreadsheet className="h-3 w-3 text-synapse-accent" />
                                  <span className="truncate max-w-[140px]">{f?.original_name || fid}</span>
                                </span>
                              );
                            })}
                          </div>
                        )}

                        {isUser ? (
                          <div className="whitespace-pre-wrap">{msg.content}</div>
                        ) : (
                          <div className="space-y-3">
                            <MarkdownMessage content={msg.content} />

                            {/* Verified Result Table */}
                            {resultData?.columns && resultData?.rows && (
                              <div className="mt-4 pt-2 border-t border-synapse-border">
                                <ResultTable
                                  columns={resultData.columns}
                                  rows={resultData.rows}
                                  durationMs={resultData.duration_ms}
                                />
                              </div>
                            )}

                            {/* Provenance & Evidence */}
                            {msg.metadata?.provenance && (
                              <SourceEvidenceCard provenance={msg.metadata.provenance} />
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {/* Streaming Status Stepper */}
              {activeAnalysisId && analysisStatus && (
                <div className="flex gap-3 items-start max-w-3xl animate-in fade-in duration-200">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-synapse-border bg-synapse-raised text-synapse-accent shadow-subtle">
                    <Layers className="h-3.5 w-3.5 animate-pulse" />
                  </div>
                  <div className="w-full">
                    <AnalysisStatusIndicator status={analysisStatus} />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* Bottom Floating Composer */}
        <div className="w-full shrink-0">
          <Composer
            files={files}
            selectedFileIds={selectedFileIds}
            onSelectFileIds={setSelectedFileIds}
            onSend={handleSendMessage}
            disabled={Boolean(activeAnalysisId)}
            onStop={() => stopActiveWork(true)}
            placeholder="Ask Universal Analyst or evaluate policy compliance..."
          />
        </div>
      </main>
    </div>
  );
}
