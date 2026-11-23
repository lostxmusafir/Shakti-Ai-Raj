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
    <div className="flex h-screen items-center justify-center bg-slate-950">
      <div className="flex flex-col items-center gap-3">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
        <p className="text-xs text-slate-400">Loading analysis workspace...</p>
      </div>
    </div>
  );
}
