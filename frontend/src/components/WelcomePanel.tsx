"use client";

import { useMemo } from "react";
import { User, ChatSession } from "@/lib/api";
import {
  BarChart3,
  ShieldCheck,
  Search,
  FileSpreadsheet,
  AlertTriangle,
  ArrowRight,
  Clock,
  Sparkles,
} from "lucide-react";

interface WelcomePanelProps {
  user: User | null;
  recentChats: ChatSession[];
  onSelectPrompt: (prompt: string) => void;
  onOpenChat: (chatId: string) => void;
}

export default function WelcomePanel({
  user,
  recentChats,
  onSelectPrompt,
  onOpenChat,
}: WelcomePanelProps) {
  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning";
    if (hour < 17) return "Good afternoon";
    return "Good evening";
  }, []);

  const firstName = user?.name ? user.name.trim().split(" ")[0] : "Analyst";

  const quickActions = [
    {
      icon: BarChart3,
      title: "Incident Overview",
      description: "Total incidents grouped by department and severity",
      prompt: "Show total incident count grouped by department where severity is High or Critical",
      tag: "Metrics",
    },
    {
      icon: ShieldCheck,
      title: "Policy Evaluation",
      description: "Verify email logs against policy SEC-EXT-001",
      prompt: "Evaluate this dataset against our email security policy for violations",
      tag: "Compliance",
    },
    {
      icon: Search,
      title: "Top External Senders",
      description: "Rank external data transfers by volume (MB)",
      prompt: "Bahar sabse zyada data kisne bheja aur total kitna MB gaya?",
      tag: "Investigation",
    },
    {
      icon: AlertTriangle,
      title: "Blocked Incident Audit",
      description: "List blocked actions and offending recipients",
      prompt: "Kitne incidents blocked hue hain aur unka action status kya hai?",
      tag: "Security",
    },
    {
      icon: FileSpreadsheet,
      title: "Internal vs External Split",
      description: "Compare internal vs external transfer volume",
      prompt: "Internal vs external split kya hai (incidents aur external MB)?",
      tag: "Distribution",
    },
    {
      icon: Sparkles,
      title: "Dataset Profile Summary",
      description: "Inspect schema, null counts, and column types",
      prompt: "Tell me about this dataset: explain the columns, records, and key metrics",
      tag: "Profiling",
    },
  ];

  function formatDisplayDate(dateStr?: string) {
    if (!dateStr) return "Recent session";
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return "Recent session";
    }
  }

  const topRecentChats = recentChats.slice(0, 3);

  return (
    <div className="flex flex-col items-center justify-center max-w-4xl mx-auto px-4 py-8 text-center animate-in fade-in duration-300">
      {/* Greeting Hero */}
      <div className="mb-6">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-synapse-border bg-synapse-raised px-3 py-1 text-xs text-synapse-secondary mb-4 shadow-subtle">
          <span className="h-2 w-2 rounded-full bg-synapse-accent animate-pulse" />
          <span>Deterministic Query Engine • Policy Verification</span>
        </div>

        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-synapse-text">
          {greeting}, <span className="text-synapse-text">{firstName}</span>
        </h1>
        <p className="mt-2 text-sm text-synapse-secondary max-w-md mx-auto">
          What would you like to analyze today? Ask questions over your data or evaluate policy rulebooks.
        </p>
      </div>

      {/* Recent Sessions Cards on Home (Synapse Style) */}
      {topRecentChats.length > 0 && (
        <div className="w-full mb-8 text-left">
          <div className="flex items-center justify-between mb-2.5 px-1">
            <span className="text-xs font-semibold uppercase tracking-wider text-synapse-muted">
              Recent Analysis Sessions
            </span>
            <span className="text-xs text-synapse-faint">Pick up where you left off</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {topRecentChats.map((chat) => (
              <button
                key={chat.id}
                type="button"
                onClick={() => onOpenChat(chat.id)}
                className="group flex flex-col justify-between rounded-xl border border-synapse-border bg-synapse-raised/90 p-3.5 text-left transition-all hover:border-synapse-border-strong hover:bg-synapse-hover shadow-subtle"
              >
                <div>
                  <div className="flex items-center justify-between text-synapse-muted mb-1.5">
                    <span className="text-[10px] font-mono flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDisplayDate(chat.updated_at || chat.created_at)}
                    </span>
                    <ArrowRight className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all text-synapse-accent" />
                  </div>
                  <h4 className="text-xs font-medium text-synapse-text truncate">
                    {chat.title || "Untitled Session"}
                  </h4>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Suggested Quick Actions */}
      <div className="w-full text-left">
        <div className="mb-2.5 px-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-synapse-muted">
            Suggested Analysis Workflows
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
          {quickActions.map((qa, idx) => {
            const Icon = qa.icon;
            return (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectPrompt(qa.prompt)}
                className="group flex flex-col justify-between rounded-xl border border-synapse-border bg-synapse-raised/60 hover:bg-synapse-raised hover:border-synapse-accent/50 p-3.5 text-left transition-all shadow-subtle"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-synapse-surface border border-synapse-border text-synapse-accent group-hover:border-synapse-accent/50 transition-colors">
                      <Icon className="h-3.5 w-3.5" />
                    </div>
                    <span className="text-[10px] font-mono text-synapse-faint group-hover:text-synapse-muted transition-colors">
                      {qa.tag}
                    </span>
                  </div>
                  <h4 className="text-xs font-medium text-synapse-text group-hover:text-synapse-text">
                    {qa.title}
                  </h4>
                  <p className="mt-1 text-[11px] text-synapse-muted line-clamp-2 leading-relaxed">
                    {qa.description}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
