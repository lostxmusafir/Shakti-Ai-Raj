"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ArrowRight, Database, Lock, Mail, ShieldCheck } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@company.internal");
  const [password, setPassword] = useState("AdminSecret123!");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api.login(email, password);
      router.push("/chat");
    } catch (err: any) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#070809] px-4 py-8 text-slate-100 sm:px-8">
      <div className="grid w-full max-w-5xl overflow-hidden border border-[#292b2f] bg-[#111214] lg:grid-cols-[1.05fr_0.95fr]">
        <section className="hidden border-r border-[#292b2f] p-10 lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--accent)] text-white">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Universal Analyst</p>
                <p className="text-xs text-slate-400">Enterprise data workspace</p>
              </div>
            </div>
            <div className="mt-20 max-w-md">
              <p className="text-3xl font-semibold tracking-tight text-white">Ask your data a better question.</p>
              <p className="mt-4 text-base leading-7 text-slate-400">
                Upload a dataset, ask in plain language, and receive a result with its source, query, and verification state attached.
              </p>
            </div>
          </div>
          <div className="grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
            <div className="border-t border-[#292b2f] pt-3">
              <div className="font-medium text-white">Verified answers</div>
              <div className="mt-1 text-slate-400">Deterministic DuckDB evidence stays close to every result.</div>
            </div>
            <div className="border-t border-[#292b2f] pt-3">
              <div className="font-medium text-white">Policy-aware access</div>
              <div className="mt-1 text-slate-400">Workspace permissions follow the authenticated account.</div>
            </div>
          </div>
        </section>

        <section className="p-6 sm:p-10">
          <div className="mb-8 lg:hidden">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--accent)] text-white">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-white">Universal Analyst</p>
                <p className="text-xs text-slate-400">Enterprise data workspace</p>
              </div>
            </div>
          </div>

          <div className="max-w-md">
            <p className="text-sm font-medium text-[var(--accent)]">Sign in</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white">Open your analysis workspace</h1>
            <p className="mt-2 text-sm leading-6 text-slate-400">Use your company account to continue to datasets, chat analysis, and policy rules.</p>
          </div>

          {error ? (
            <div role="alert" className="mt-6 border border-red-500/30 bg-red-500/[0.06] p-3 text-sm text-red-200">
              {error}
            </div>
          ) : null}

          <form onSubmit={handleSubmit} className="mt-8 max-w-md space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-200">Company email</label>
              <div className="relative mt-2">
                <Mail aria-hidden="true" className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" />
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="h-11 w-full rounded-md border border-[#42454b] bg-[#0b0c0e] py-2 pl-10 pr-3 text-sm text-white placeholder:text-slate-600 focus:border-[var(--accent)] focus:outline-none"
                  placeholder="you@company.com"
                />
              </div>
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-200">Password</label>
              <div className="relative mt-2">
                <Lock aria-hidden="true" className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" />
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 w-full rounded-md border border-[#42454b] bg-[#0b0c0e] py-2 pl-10 pr-3 text-sm text-white placeholder:text-slate-600 focus:border-[var(--accent)] focus:outline-none"
                  placeholder="Enter your password"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="accent-action flex h-11 w-full items-center justify-center gap-2 rounded-md text-sm font-semibold transition disabled:cursor-wait disabled:opacity-50"
            >
              {loading ? "Signing in…" : "Continue to workspace"}
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          </form>

          <div className="mt-10 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-[#292b2f] pt-4 text-xs text-slate-400">
            <span className="flex items-center gap-1.5"><Database className="h-3.5 w-3.5 text-emerald-400" /> Isolated data access</span>
            <span>RBAC protected</span>
          </div>
        </section>
      </div>
    </main>
  );
}
