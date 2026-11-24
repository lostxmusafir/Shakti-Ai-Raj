"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ShieldCheck, ArrowRight, Lock, Mail, Database, Layers, CheckCircle2 } from "lucide-react";

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
    <div className="flex min-h-screen items-center justify-center bg-synapse-bg px-4 selection:bg-synapse-accent/30 selection:text-white">
      <div className="w-full max-w-sm rounded-2xl border border-synapse-border bg-synapse-surface p-7 shadow-composer backdrop-blur-xl">
        {/* Brand Header */}
        <div className="flex flex-col items-center text-center">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-synapse-raised border border-synapse-border text-synapse-accent shadow-subtle mb-3">
            <Layers className="h-5 w-5" />
          </div>
          <h1 className="text-xl font-bold tracking-tight text-synapse-text">
            Universal Analyst
          </h1>
          <p className="mt-1 text-xs text-synapse-secondary">
            Deterministic Enterprise Intelligence Workspace
          </p>
        </div>

        {error && (
          <div className="mt-5 rounded-xl border border-red-800/40 bg-red-950/40 p-3 text-xs text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
          <div>
            <label className="block text-[11px] font-medium text-synapse-secondary mb-1">
              Company Email
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-2.5 h-3.5 w-3.5 text-synapse-muted" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-synapse-border bg-synapse-raised py-2 pl-9 pr-3 text-xs text-synapse-text placeholder-synapse-muted focus:border-synapse-accent focus:outline-none transition-colors"
                placeholder="you@company.internal"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-medium text-synapse-secondary mb-1">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 h-3.5 w-3.5 text-synapse-muted" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-xl border border-synapse-border bg-synapse-raised py-2 pl-9 pr-3 text-xs text-synapse-text placeholder-synapse-muted focus:border-synapse-accent focus:outline-none transition-colors"
                placeholder="••••••••"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-synapse-accent hover:bg-synapse-accent-hover py-2.5 text-xs font-semibold text-white shadow-subtle transition-colors disabled:opacity-50"
          >
            <span>{loading ? "Signing in..." : "Enter Workspace"}</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </form>

        <div className="mt-6 border-t border-synapse-border pt-3.5">
          <div className="flex items-center justify-between text-[11px] text-synapse-muted">
            <span className="flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Isolated Tenancy
            </span>
            <span>RBAC Protected</span>
          </div>
        </div>
      </div>
    </div>
  );
}
