"use client";

import Link from "next/navigation";
import { useRouter, usePathname } from "next/navigation";
import { User, ChatSession, clearStoredToken } from "@/lib/api";
import {
  MessageSquare,
  FileSpreadsheet,
  ShieldAlert,
  Plus,
  LogOut,
  Database,
  Layers,
} from "lucide-react";

interface SidebarProps {
  user: User | null;
  chats: ChatSession[];
  activeChatId?: string;
  onNewChat: () => void;
}

export default function Sidebar({
  user,
  chats,
  activeChatId,
  onNewChat,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();

  const handleLogout = () => {
    clearStoredToken();
    router.push("/login");
  };

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-slate-800 bg-slate-900/95">
      {/* Brand Header */}
      <div className="flex h-16 items-center gap-2.5 border-b border-slate-800 px-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30">
          <Layers className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-white">
            Universal Analyst
          </h2>
          <span className="text-[10px] font-medium uppercase tracking-wider text-indigo-400">
            Enterprise AI
          </span>
        </div>
      </div>

      {/* Navigation */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 py-2 px-3 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-500"
        >
          <Plus className="h-3.5 w-3.5" />
          New Analysis
        </button>

        <nav className="mt-4 space-y-1">
          <button
            onClick={() => router.push("/chat")}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              pathname?.startsWith("/chat")
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <MessageSquare className="h-4 w-4" />
            AI Chat Analysis
          </button>
          <button
            onClick={() => router.push("/files")}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              pathname === "/files"
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <FileSpreadsheet className="h-4 w-4" />
            Datasets & Profiler
          </button>
          <button
            onClick={() => router.push("/policies")}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
              pathname === "/policies"
                ? "bg-slate-800 text-white"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <ShieldAlert className="h-4 w-4" />
            Policy Rule Books
          </button>
        </nav>
      </div>

      {/* Chat Sessions History */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <div className="mb-2 px-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          Recent Sessions
        </div>
        <div className="space-y-1">
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => router.push(`/chat/${chat.id}`)}
              className={`flex w-full items-center gap-2 truncate rounded-md px-2 py-1.5 text-left text-xs transition ${
                activeChatId === chat.id
                  ? "bg-indigo-950/60 text-indigo-300 ring-1 ring-indigo-500/30"
                  : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-300"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-70" />
              <span className="truncate">{chat.title || "Untitled Session"}</span>
            </button>
          ))}
        </div>
      </div>

      {/* User Footer */}
      <div className="border-t border-slate-800 p-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-slate-300">
              {user?.name ? user.name[0].toUpperCase() : "U"}
            </div>
            <div className="truncate">
              <div className="truncate text-xs font-medium text-slate-200">
                {user?.name || "User"}
              </div>
              <div className="text-[10px] text-slate-500">
                {user?.role || "employee"} • {user?.unit_id || "global"}
              </div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-red-400"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
