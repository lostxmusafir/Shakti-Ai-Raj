"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Policy, User, ChatSession } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import {
  ShieldCheck,
  ShieldAlert,
  Calendar,
  Building,
  CheckCircle2,
  Search,
  Filter,
  Layers,
  ArrowRight,
} from "lucide-react";

export default function PoliciesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("all");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [me, chatList, policyList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.listPolicies(),
        ]);
        if (cancelled) return;
        setUser(me);
        setChats(chatList);
        setPolicies(policyList);
      } catch {
        if (!cancelled) router.push("/login");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const departments = Array.from(new Set(policies.map((p) => p.department).filter(Boolean)));

  const filteredPolicies = policies.filter((p) => {
    const matchesSearch =
      p.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.policy_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesDept = departmentFilter === "all" || p.department === departmentFilter;
    return matchesSearch && matchesDept;
  });

  const handleAuditInChat = (policyCode: string) => {
    const prompt = `Evaluate recent datasets against policy ${policyCode} and report all violating records`;
    router.push(`/chat?prompt=${encodeURIComponent(prompt)}`);
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-synapse-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 rounded-full border-2 border-synapse-border border-t-synapse-accent animate-spin" />
          <p className="text-xs text-synapse-muted">Loading policy rule books...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-synapse-bg text-synapse-text overflow-hidden">
      <Sidebar
        user={user}
        chats={chats}
        onNewChat={() => router.push("/chat")}
        onDeleteChat={async (chatId) => {
          try {
            await api.deleteChat(chatId);
            setChats((prev) => prev.filter((chat) => chat.id !== chatId));
          } catch (err: any) {
            alert(err.message || "Failed to delete chat.");
          }
        }}
      />

      <main className="flex flex-1 flex-col overflow-y-auto p-4 sm:p-8 pt-16 lg:pt-8">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-synapse-border">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-synapse-text">
              Company Policy Rule Books
            </h1>
            <p className="mt-1 text-xs text-synapse-secondary">
              Version-controlled compliance rules evaluated deterministically against tabular datasets with exact row evidence.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-synapse-border bg-synapse-surface px-3 py-1 text-xs font-medium text-synapse-secondary">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              <span>{policies.length} Active Policies</span>
            </span>
          </div>
        </div>

        {/* Filter Toolbar */}
        <div className="mt-6 flex flex-col sm:flex-row items-center gap-3">
          <div className="relative w-full sm:w-72">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-synapse-muted" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by code, title, keyword..."
              className="w-full rounded-xl border border-synapse-border bg-synapse-surface py-2 pl-9 pr-3 text-xs text-synapse-text placeholder-synapse-muted focus:border-synapse-accent focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0">
            <button
              onClick={() => setDepartmentFilter("all")}
              className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-colors border ${
                departmentFilter === "all"
                  ? "bg-synapse-raised text-synapse-text border-synapse-border-strong"
                  : "bg-synapse-surface text-synapse-secondary border-synapse-border hover:bg-synapse-hover"
              }`}
            >
              All Departments
            </button>
            {departments.map((dept) => (
              <button
                key={dept}
                onClick={() => setDepartmentFilter(dept)}
                className={`rounded-xl px-3 py-1.5 text-xs font-medium transition-colors border whitespace-nowrap ${
                  departmentFilter === dept
                    ? "bg-synapse-raised text-synapse-text border-synapse-border-strong"
                    : "bg-synapse-surface text-synapse-secondary border-synapse-border hover:bg-synapse-hover"
                }`}
              >
                {dept}
              </button>
            ))}
          </div>
        </div>

        {/* Policies Grid */}
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filteredPolicies.length === 0 ? (
            <div className="col-span-full flex flex-col items-center justify-center rounded-2xl border border-dashed border-synapse-border p-12 text-center bg-synapse-surface/40">
              <ShieldAlert className="h-8 w-8 text-synapse-muted mb-2" />
              <p className="text-sm font-semibold text-synapse-text">No matching policies found</p>
              <p className="text-xs text-synapse-muted mt-1">Try adjusting your search query or department filter.</p>
            </div>
          ) : (
            filteredPolicies.map((p) => (
              <div
                key={p.id}
                className="flex flex-col justify-between rounded-2xl border border-synapse-border bg-synapse-surface p-5 shadow-card hover:border-synapse-border-strong transition-all"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-synapse-raised border border-synapse-border text-synapse-accent">
                        <ShieldCheck className="h-5 w-5" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold text-synapse-accent">
                            {p.policy_code}
                          </span>
                          <span className="rounded bg-synapse-raised border border-synapse-border px-1.5 py-0.2 text-[10px] font-mono text-synapse-muted">
                            v{p.version}
                          </span>
                        </div>
                        <h3 className="text-sm font-semibold text-synapse-text mt-0.5">
                          {p.title}
                        </h3>
                      </div>
                    </div>

                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950/70 border border-emerald-800/40 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                      Active
                    </span>
                  </div>

                  <p className="mt-3 text-xs text-synapse-secondary leading-relaxed">
                    {p.description}
                  </p>

                  <div className="mt-3.5 flex flex-wrap items-center gap-3 text-xs text-synapse-muted">
                    <span className="flex items-center gap-1.5">
                      <Building className="h-3.5 w-3.5 text-synapse-faint" />
                      <span>{p.department}</span>
                    </span>
                    <span>•</span>
                    <span className="flex items-center gap-1.5">
                      <Calendar className="h-3.5 w-3.5 text-synapse-faint" />
                      <span>Effective: {p.effective_from}</span>
                    </span>
                  </div>

                  {/* Evaluation Rules */}
                  <div className="mt-4 pt-3.5 border-t border-synapse-border/60">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-synapse-muted block mb-2">
                      Rules ({p.rules?.length || 0})
                    </span>

                    <div className="space-y-1.5">
                      {p.rules?.map((r) => {
                        const isCritical = r.severity.toLowerCase() === "critical";
                        const isHigh = r.severity.toLowerCase() === "high";

                        return (
                          <div
                            key={r.rule_id}
                            className="rounded-xl border border-synapse-border/80 bg-synapse-raised/50 p-2.5 text-xs"
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className="font-mono text-[10px] text-synapse-accent">
                                {r.rule_id}
                              </span>
                              <span
                                className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase border ${
                                  isCritical
                                    ? "bg-red-950/60 text-red-300 border-red-800/40"
                                    : isHigh
                                    ? "bg-amber-950/60 text-amber-300 border-amber-800/40"
                                    : "bg-blue-950/60 text-blue-300 border-blue-800/40"
                                }`}
                              >
                                {r.severity}
                              </span>
                            </div>
                            <p className="text-xs text-synapse-text">{r.description}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-synapse-border/60 flex justify-end">
                  <button
                    onClick={() => handleAuditInChat(p.policy_code)}
                    className="flex items-center gap-1 text-xs text-synapse-accent hover:text-synapse-accent-hover font-medium transition-colors"
                  >
                    <span>Run Policy Audit in Chat</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
