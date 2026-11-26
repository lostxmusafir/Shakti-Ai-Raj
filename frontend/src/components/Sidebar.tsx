"use client";

import { useRouter, usePathname } from "next/navigation";
import { User, ChatSession, api } from "@/lib/api";
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

  const handleLogout = async () => {
    await api.logout();
    router.push("/login");
  };

  return (
    <aside className="app-sidebar flex h-screen w-[252px] shrink-0 flex-col border-r">
      {/* Brand Header */}
      <div className="sidebar-brand flex h-[72px] items-center gap-3 border-b px-4">
        <div className="sidebar-brand-mark flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-indigo-500 text-white">
          <Layers className="h-5 w-5" />
        </div>
        <div className="sidebar-label min-w-0">
          <h2 className="truncate text-[13px] font-semibold tracking-tight text-white">
            Universal Analyst
          </h2>
          <span className="text-[10px] font-medium text-indigo-300">
            Enterprise AI
          </span>
        </div>
      </div>

      {/* Navigation */}
      <div className="p-3">
        <button
          onClick={onNewChat}
          className="sidebar-action accent-action flex w-full items-center justify-center gap-2 rounded-lg py-2.5 px-3 text-xs font-semibold text-white transition"
        >
          <Plus className="h-3.5 w-3.5" />
          New Analysis
        </button>

        <nav className="mt-5 space-y-1">
          <button
            onClick={() => router.push("/chat")}
            className={`sidebar-nav-item flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium transition ${
              pathname?.startsWith("/chat")
                ? "bg-white/[0.08] text-white"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
            }`}
          >
            <MessageSquare className="h-4 w-4" />
            <span className="sidebar-label">AI Chat Analysis</span>
          </button>
          <button
            onClick={() => router.push("/files")}
            className={`sidebar-nav-item flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium transition ${
              pathname === "/files"
                ? "bg-white/[0.08] text-white"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
            }`}
          >
            <FileSpreadsheet className="h-4 w-4" />
            <span className="sidebar-label">Datasets & Profiler</span>
          </button>
          <button
            onClick={() => router.push("/policies")}
            className={`sidebar-nav-item flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium transition ${
              pathname === "/policies"
                ? "bg-white/[0.08] text-white"
                : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-200"
            }`}
          >
            <ShieldAlert className="h-4 w-4" />
            <span className="sidebar-label">Policy Rule Books</span>
          </button>
        </nav>
      </div>

      {/* Chat Sessions History */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <div className="sidebar-section-label mb-2 px-2 text-[10px] font-medium uppercase tracking-[0.14em] text-slate-600">
          Recent Sessions
        </div>
        <div className="space-y-1">
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => router.push(`/chat/${chat.id}`)}
              className={`flex w-full items-center gap-2 truncate rounded-md px-2 py-1.5 text-left text-xs transition ${
                activeChatId === chat.id
                  ? "bg-indigo-500/10 text-indigo-200 ring-1 ring-indigo-400/20"
                  : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-300"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 shrink-0 opacity-70" />
              <span className="sidebar-label truncate">{chat.title || "Untitled Session"}</span>
            </button>
          ))}
        </div>
      </div>

      {/* User Footer */}
      <div className="border-t border-slate-800 p-3">
        <div className="sidebar-user flex items-center justify-between">
          <div className="flex items-center gap-2 overflow-hidden">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-slate-300">
              {user?.name ? user.name[0].toUpperCase() : "U"}
            </div>
            <div className="sidebar-user-copy truncate">
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
            className="sidebar-logout rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-red-400"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
