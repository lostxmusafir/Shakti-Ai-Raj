"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Policy, User, ChatSession } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import { ShieldCheck, ShieldAlert, Calendar, Building, CheckCircle2 } from "lucide-react";

export default function PoliciesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [me, chatList, policyList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.listPolicies(),
        ]);
        setUser(me);
        setChats(chatList);
        setPolicies(policyList);
      } catch {
        router.push("/login");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [router]);

  return (
    <div className="app-main flex h-screen">
      <Sidebar
        user={user}
        chats={chats}
        onNewChat={() => router.push("/chat")}
      />

      <main className="app-main flex min-w-0 flex-1 flex-col overflow-y-auto px-5 py-6 sm:px-8 sm:py-8">
        <div className="page-header border-b pb-6">
          <h1 className="text-2xl font-semibold tracking-[-0.03em] text-white">
            Company Policy Rule Books
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
            Version-controlled organizational rules used by the AI engine to evaluate tabular dataset compliance.
          </p>
        </div>

        <div className="mx-auto mt-7 grid w-full max-w-[1180px] grid-cols-1 gap-4 xl:grid-cols-2">
          {policies.map((p) => (
            <div
              key={p.id}
              className="surface-panel rounded-xl border p-6"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-300 ring-1 ring-indigo-400/20">
                    <ShieldCheck className="h-6 w-6" />
                  </div>
                  <div>
                    <span className="font-mono text-xs font-semibold text-indigo-400">
                      {p.policy_code} • v{p.version}
                    </span>
                    <h3 className="text-base font-semibold text-white">{p.title}</h3>
                  </div>
                </div>

                <span className="rounded-full bg-emerald-950 px-2.5 py-0.5 text-[10px] font-bold uppercase text-emerald-400 border border-emerald-800">
                  Active
                </span>
              </div>

              <p className="mt-3 text-xs text-slate-400 leading-relaxed">
                {p.description}
              </p>

              <div className="mt-4 flex items-center gap-4 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <Building className="h-3.5 w-3.5 text-slate-400" />
                  {p.department}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="h-3.5 w-3.5 text-slate-400" />
                  Effective: {p.effective_from}
                </span>
              </div>

              {/* Rules List */}
              <div className="mt-5 border-t border-slate-800 pt-4">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Machine-Readable Evaluation Rules
                </div>
                <div className="space-y-2">
                  {p.rules?.map((r) => (
                    <div
                      key={r.rule_id}
                      className="rounded-lg border border-slate-800/80 bg-slate-950/60 p-2.5 text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-[10px] text-indigo-300">
                          {r.rule_id}
                        </span>
                        <span className="rounded bg-red-950/80 px-1.5 py-0.5 text-[10px] font-medium text-red-300 border border-red-800/40">
                          {r.severity.toUpperCase()}
                        </span>
                      </div>
                      <p className="mt-1 text-slate-300">{r.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
