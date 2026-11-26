"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { ShieldCheck, ArrowRight, Lock, Mail, Database } from "lucide-react";

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
    <div className="flex min-h-screen items-center justify-center bg-[#090a0d] px-4 py-10">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-[#111318] p-8 shadow-2xl shadow-black/30">
        <div className="flex flex-col items-center text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-indigo-500/10 text-indigo-300 ring-1 ring-indigo-400/20">
            <ShieldCheck className="h-8 w-8" />
          </div>
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white">
            Universal AI Analyst
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Internal Policy-Aware Enterprise Data Intelligence
          </p>
        </div>

        {error && (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-950/40 p-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-300">
              Company Email
            </label>
            <div className="relative mt-1">
              <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 pl-9 pr-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="you@company.com"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300">
              Password
            </label>
            <div className="relative mt-1">
              <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 pl-9 pr-3 text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                placeholder="••••••••"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="accent-action flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold text-white transition disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign in to Workspace"}
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>

        <div className="mt-6 border-t border-slate-800 pt-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span className="flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-emerald-400" />
              MongoDB Atlas Isolated
            </span>
            <span>RBAC Protected</span>
          </div>
        </div>
      </div>
    </div>
  );
}
