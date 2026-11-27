"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ChatSession, User } from "@/lib/api";
import Sidebar from "@/components/Sidebar";

export default function ChatIndexPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function init() {
      try {
        const chats = await api.listChats();
        if (chats.length > 0) {
          router.push(`/chat/${chats[0].id}`);
        } else {
          const newChat = await api.createChat("Initial Analysis Session");
          router.push(`/chat/${newChat.id}`);
        }
      } catch (err) {
        router.push("/login");
      }
    }
    init();
  }, [router]);

  return (
    <div className="flex h-screen items-center justify-center bg-[var(--background)]">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-[var(--accent)]"></div>
        <p className="text-sm text-slate-400">Opening analysis workspace…</p>
      </div>
    </div>
  );
}
