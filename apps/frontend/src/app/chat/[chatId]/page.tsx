"use client";

import { useEffect, useState, useRef, use } from "react";
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
import { Sparkles, Bot, User as UserIcon, ShieldAlert } from "lucide-react";

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
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, analysisStatus]);

  // Load initial session data
  useEffect(() => {
    async function loadData() {
      try {
        const [me, chatList, msgList, fileList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.getMessages(chatId),
          api.listFiles(),
        ]);
        setUser(me);
        setChats(chatList);
        setMessages(msgList);
        setFiles(fileList);
        if (fileList.length > 0 && selectedFileIds.length === 0) {
          // Pre-select first file for convenience
          setSelectedFileIds([fileList[0].id]);
        }
      } catch (err) {
        router.push("/login");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [chatId, router]);

  // SSE stream listener when activeAnalysisId is set
  useEffect(() => {
    if (!activeAnalysisId) return;

    const eventSource = new EventSource(
      `http://localhost:8000/api/v1/analysis/${activeAnalysisId}/events`
    );

    eventSource.addEventListener("analysis.status", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        setAnalysisStatus(data.status);
      } catch {}
    });

    eventSource.addEventListener("assistant.delta", (e: any) => {
      // streaming delta chunks
    });

    eventSource.addEventListener("analysis.completed", (e: any) => {
      try {
        const data = JSON.parse(e.data);
        setAnalysisStatus("completed");
        setAnalysisResult(data.result);
        // Refresh message list
        api.getMessages(chatId).then(setMessages);
      } catch {}
      eventSource.close();
      setActiveAnalysisId(null);
    });

    eventSource.addEventListener("analysis.failed", (e: any) => {
      setAnalysisStatus("failed");
      eventSource.close();
      setActiveAnalysisId(null);
    });

    eventSource.onerror = () => {
      // Polling fallback
      const timer = setInterval(async () => {
        try {
          const ana = await api.getAnalysis(activeAnalysisId);
          if (ana.status === "completed" || ana.status === "failed") {
            setAnalysisStatus(ana.status);
            setAnalysisResult(ana.result);
            clearInterval(timer);
            setActiveAnalysisId(null);
            api.getMessages(chatId).then(setMessages);
          } else {
            setAnalysisStatus(ana.status);
          }
        } catch {
          clearInterval(timer);
        }
      }, 1000);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [activeAnalysisId, chatId]);

  const handleSendMessage = async (content: string, fileIds: string[]) => {
    try {
      // Optimistic user message
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
      setAnalysisResult(null);

      const resp = await api.sendMessage(chatId, content, fileIds);
      if (resp.analysis_id) {
        setActiveAnalysisId(resp.analysis_id);
      }
    } catch (err: any) {
      alert(err.message || "Failed to send message.");
    }
  };

  const handleNewChat = async () => {
    try {
      const newSession = await api.createChat("New Analysis");
      router.push(`/chat/${newSession.id}`);
    } catch (err: any) {
      alert("Failed to create chat");
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-950">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  const currentChat = chats.find((c) => c.id === chatId);

  return (
    <div className="flex h-screen bg-slate-950">
      <Sidebar
        user={user}
        chats={chats}
        activeChatId={chatId}
        onNewChat={handleNewChat}
      />

      <main className="flex flex-1 flex-col overflow-hidden">
        {/* Chat Header */}
        <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-900/60 px-6 backdrop-blur-md">
          <div>
            <h1 className="text-sm font-semibold text-white">
              {currentChat?.title || "Data Analysis Session"}
            </h1>
            <p className="text-[11px] text-slate-400">
              Deterministic Query Engine • Policy Verification Enabled
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 rounded-full bg-emerald-950 px-2.5 py-1 text-xs font-medium text-emerald-400 border border-emerald-800/60">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              Engine Online
            </span>
          </div>
        </header>

        {/* Message Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600/20 text-indigo-400 ring-1 ring-indigo-500/30">
                <Sparkles className="h-6 w-6" />
              </div>
              <h2 className="mt-4 text-base font-semibold text-white">
                Start Analytical Investigation
              </h2>
              <p className="mt-1 max-w-sm text-xs text-slate-400">
                Ask questions over your datasets. Calculations execute through DuckDB and verify against company policy rule books.
              </p>

              <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-md">
                <button
                  onClick={() =>
                    handleSendMessage(
                      "Show total incident count grouped by department where severity is Critical",
                      selectedFileIds
                    )
                  }
                  className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-300 hover:border-indigo-500 hover:text-white transition text-left"
                >
                  📊 "Show incident count by department for Critical severity"
                </button>
                <button
                  onClick={() =>
                    handleSendMessage(
                      "Evaluate this dataset against our email security policy for violations",
                      selectedFileIds
                    )
                  }
                  className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-300 hover:border-indigo-500 hover:text-white transition text-left"
                >
                  🛡️ "Check email logs against security policy SEC-EMAIL-001"
                </button>
              </div>
            </div>
          ) : (
            messages.map((msg) => {
              const isUser = msg.role === "user";
              return (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
                >
                  {!isUser && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30">
                      <Bot className="h-4 w-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-2xl rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                      isUser
                        ? "bg-indigo-600 text-white shadow-lg shadow-indigo-600/20"
                        : "border border-slate-800 bg-slate-900/90 text-slate-200 backdrop-blur-md"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>

                  {isUser && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-slate-300">
                      <UserIcon className="h-4 w-4" />
                    </div>
                  )}
                </div>
              );
            })
          )}

          {/* Active Status Stepper */}
          {activeAnalysisId && analysisStatus && (
            <div className="flex gap-3 justify-start">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white">
                <Bot className="h-4 w-4" />
              </div>
              <div className="w-full max-w-2xl">
                <AnalysisStatusIndicator status={analysisStatus} />
              </div>
            </div>
          )}

          {/* Result Table Preview if available */}
          {analysisResult?.columns && analysisResult?.rows && (
            <div className="pl-11 max-w-3xl">
              <ResultTable
                columns={analysisResult.columns}
                rows={analysisResult.rows}
                durationMs={analysisResult.duration_ms}
              />
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Composer */}
        <Composer
          files={files}
          selectedFileIds={selectedFileIds}
          onSelectFileIds={setSelectedFileIds}
          onSend={handleSendMessage}
          disabled={Boolean(activeAnalysisId)}
        />
      </main>
    </div>
  );
}
