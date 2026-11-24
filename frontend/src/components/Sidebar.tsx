"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { User, ChatSession, api } from "@/lib/api";
import {
  MessageSquare,
  FileSpreadsheet,
  ShieldAlert,
  Plus,
  LogOut,
  Layers,
  Trash2,
  Menu,
  X,
  Sparkles,
} from "lucide-react";

interface SidebarProps {
  user: User | null;
  chats: ChatSession[];
  activeChatId?: string;
  onNewChat: () => void;
  onDeleteChat?: (chatId: string) => void | Promise<void>;
}

export default function Sidebar({
  user,
  chats,
  activeChatId,
  onNewChat,
  onDeleteChat,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleLogout = async () => {
    await api.logout();
    router.push("/login");
  };

  const handleDelete = async (e: React.MouseEvent, chatId: string, title?: string) => {
    e.stopPropagation();
    if (!onDeleteChat) return;
    if (window.confirm(`Delete "${title || "this chat"}"? Messages and analysis run history will be removed.`)) {
      setDeletingId(chatId);
      try {
        await onDeleteChat(chatId);
      } finally {
        setDeletingId(null);
      }
    }
  };

  const navItems = [
    {
      label: "AI Chat Analysis",
      href: "/chat",
      icon: MessageSquare,
      active: pathname?.startsWith("/chat"),
    },
    {
      label: "Datasets & Profiler",
      href: "/files",
      icon: FileSpreadsheet,
      active: pathname === "/files",
    },
    {
      label: "Policy Rule Books",
      href: "/policies",
      icon: ShieldAlert,
      active: pathname === "/policies",
    },
  ];

  const content = (
    <div className="flex h-full w-full flex-col justify-between bg-synapse-surface text-synapse-text border-r border-synapse-border">
      {/* Brand Header */}
      <div className="flex flex-col">
        <div className="flex h-16 items-center justify-between px-4 border-b border-synapse-border-subtle">
          <div
            onClick={() => router.push("/chat")}
            className="flex items-center gap-2.5 cursor-pointer group"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-synapse-raised border border-synapse-border text-synapse-accent shadow-subtle group-hover:border-synapse-accent transition-colors">
              <Layers className="h-4.5 w-4.5" />
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold tracking-tight text-synapse-text flex items-center gap-1.5">
                Universal Analyst
              </span>
              <span className="text-[10px] font-medium tracking-wide text-synapse-muted">
                Deterministic AI
              </span>
            </div>
          </div>

          {/* Mobile close button */}
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden rounded-lg p-1 text-synapse-muted hover:text-synapse-text hover:bg-synapse-hover"
            aria-label="Close menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Action: New Analysis */}
        <div className="p-3">
          <button
            onClick={() => {
              onNewChat();
              setMobileOpen(false);
            }}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-synapse-raised hover:bg-synapse-hover text-synapse-text border border-synapse-border hover:border-synapse-accent px-3 py-2.5 text-xs font-medium shadow-subtle transition-all duration-150 group"
          >
            <Plus className="h-3.5 w-3.5 text-synapse-accent group-hover:scale-110 transition-transform" />
            <span>New Analysis</span>
          </button>
        </div>

        {/* Primary Navigation */}
        <nav className="px-3 py-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.href}
                onClick={() => {
                  router.push(item.href);
                  setMobileOpen(false);
                }}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium transition-colors ${
                  item.active
                    ? "bg-synapse-raised text-synapse-text border border-synapse-border-strong"
                    : "text-synapse-secondary hover:bg-synapse-hover hover:text-synapse-text border border-transparent"
                }`}
              >
                <Icon className={`h-4 w-4 ${item.active ? "text-synapse-accent" : "text-synapse-muted"}`} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Divider */}
        <div className="mx-4 my-2 border-t border-synapse-border-subtle" />

        {/* Recent Sessions */}
        <div className="px-3 flex items-center justify-between py-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-synapse-faint">
            Recent Sessions
          </span>
          <span className="text-[10px] font-mono text-synapse-muted">
            {chats.length}
          </span>
        </div>
      </div>

      {/* Chat History List */}
      <div className="flex-1 overflow-y-auto px-3 py-1 space-y-1">
        {chats.length === 0 ? (
          <div className="px-2 py-6 text-center">
            <p className="text-xs text-synapse-faint">No previous sessions</p>
          </div>
        ) : (
          chats.map((chat) => {
            const isActive = activeChatId === chat.id;
            return (
              <div
                key={chat.id}
                onClick={() => {
                  router.push(`/chat/${chat.id}`);
                  setMobileOpen(false);
                }}
                className={`group relative flex w-full cursor-pointer items-center justify-between rounded-lg px-2.5 py-2 text-xs transition-colors border ${
                  isActive
                    ? "bg-synapse-raised text-synapse-text border-synapse-border-strong font-medium"
                    : "text-synapse-secondary hover:bg-synapse-hover hover:text-synapse-text border-transparent"
                }`}
              >
                <div className="flex min-w-0 items-center gap-2 truncate">
                  <MessageSquare
                    className={`h-3.5 w-3.5 shrink-0 ${
                      isActive ? "text-synapse-accent" : "text-synapse-muted group-hover:text-synapse-secondary"
                    }`}
                  />
                  <span className="truncate">{chat.title || "Untitled Session"}</span>
                </div>

                {/* Subtle hover delete action */}
                {onDeleteChat && (
                  <button
                    type="button"
                    onClick={(e) => handleDelete(e, chat.id, chat.title)}
                    disabled={deletingId === chat.id}
                    title="Delete session"
                    aria-label={`Delete ${chat.title || "session"}`}
                    className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 rounded p-1 text-synapse-muted hover:text-synapse-danger hover:bg-synapse-surface shrink-0"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* User Profile Footer */}
      <div className="border-t border-synapse-border p-3 bg-synapse-surface">
        <div className="flex items-center justify-between rounded-xl p-1.5 hover:bg-synapse-hover transition-colors">
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-synapse-raised border border-synapse-border text-xs font-semibold text-synapse-accent">
              {user?.name ? user.name.slice(0, 2).toUpperCase() : "UA"}
            </div>
            <div className="truncate text-left">
              <div className="truncate text-xs font-medium text-synapse-text">
                {user?.name || "Analyst User"}
              </div>
              <div className="text-[10px] text-synapse-muted flex items-center gap-1.5">
                <span className="capitalize">{user?.role || "employee"}</span>
                <span>•</span>
                <span className="truncate">{user?.unit_id || "global"}</span>
              </div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            title="Sign out"
            aria-label="Sign out"
            className="rounded-lg p-1.5 text-synapse-muted hover:text-synapse-danger hover:bg-synapse-raised transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Mobile top trigger bar */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-40 flex h-14 items-center justify-between border-b border-synapse-border bg-synapse-surface px-4">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setMobileOpen(true)}
            className="rounded-lg p-1.5 text-synapse-secondary hover:bg-synapse-hover"
            aria-label="Open sidebar"
          >
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-xs font-semibold text-synapse-text">Universal Analyst</span>
        </div>
        <button
          onClick={onNewChat}
          className="flex items-center gap-1 rounded-lg bg-synapse-raised border border-synapse-border px-2.5 py-1 text-xs text-synapse-text hover:border-synapse-accent"
        >
          <Plus className="h-3 w-3 text-synapse-accent" />
          <span>New</span>
        </button>
      </div>

      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:flex h-screen w-64 shrink-0 flex-col">
        {content}
      </aside>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 z-50 flex">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity"
            onClick={() => setMobileOpen(false)}
          />
          <div className="relative flex w-72 flex-col">
            {content}
          </div>
        </div>
      )}
    </>
  );
}
