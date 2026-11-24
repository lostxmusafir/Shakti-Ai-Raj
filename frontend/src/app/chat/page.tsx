"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  User,
  ChatSession,
  StoredFile,
} from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import Composer from "@/components/Composer";
import WelcomePanel from "@/components/WelcomePanel";

export default function ChatIndexPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [me, chatList, fileList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.listFiles(),
        ]);
        if (cancelled) return;
        setUser(me);
        setChats(chatList);
        setFiles(fileList);
      } catch (err) {
        if (!cancelled) router.push("/login");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const handleStartPrompt = async (promptContent: string, fileIds: string[] = selectedFileIds) => {
    if (!promptContent.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      // Generate clean title from prompt
      const title = promptContent.length > 36 ? promptContent.slice(0, 36) + "..." : promptContent;
      const newSession = await api.createChat(title);
      // Store the initial message in session storage to be picked up by the chat detail page
      if (typeof window !== "undefined") {
        sessionStorage.setItem(
          `pending_prompt_${newSession.id}`,
          JSON.stringify({ content: promptContent, fileIds })
        );
      }
      router.push(`/chat/${newSession.id}`);
    } catch (err: any) {
      alert(err.message || "Failed to start analysis session.");
      setIsSubmitting(false);
    }
  };

  const handleDeleteChat = async (deletedChatId: string) => {
    try {
      await api.deleteChat(deletedChatId);
      setChats((prev) => prev.filter((chat) => chat.id !== deletedChatId));
    } catch (err: any) {
      alert(err.message || "Failed to delete chat.");
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

  return (
    <div className="flex h-screen bg-synapse-bg text-synapse-text overflow-hidden">
      <Sidebar
        user={user}
        chats={chats}
        onNewChat={() => {}}
        onDeleteChat={handleDeleteChat}
      />

      <main className="flex flex-1 flex-col overflow-hidden relative pt-14 lg:pt-0">
        {/* Workspace Top Bar */}
        <header className="hidden lg:flex h-14 items-center justify-between border-b border-synapse-border bg-synapse-surface/60 px-6 backdrop-blur-md">
          <div className="flex items-center gap-3">
            <h2 className="text-xs font-semibold text-synapse-text">New Analysis</h2>
            <span className="text-[11px] text-synapse-muted">
              Select an action or ask a custom analytical query
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-synapse-border bg-synapse-raised px-2.5 py-0.5 text-[11px] text-synapse-secondary">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Engine Ready
            </span>
          </div>
        </header>

        {/* Scrollable Workspace Center */}
        <div className="flex-1 overflow-y-auto px-4 py-6 flex flex-col justify-center">
          <WelcomePanel
            user={user}
            recentChats={chats}
            onSelectPrompt={(prompt) => handleStartPrompt(prompt, selectedFileIds)}
            onOpenChat={(chatId) => router.push(`/chat/${chatId}`)}
          />
        </div>

        {/* Floating Centered Composer */}
        <div className="w-full shrink-0">
          <Composer
            files={files}
            selectedFileIds={selectedFileIds}
            onSelectFileIds={setSelectedFileIds}
            onSend={(content, fileIds) => handleStartPrompt(content, fileIds)}
            disabled={isSubmitting}
            placeholder="Ask Universal Analyst or evaluate policy compliance..."
          />
        </div>
      </main>
    </div>
  );
}
