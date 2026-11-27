"use client";

import { useEffect, useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { api, StoredFile, User, ChatSession } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import {
  UploadCloud,
  FileSpreadsheet,
  Trash2,
  MessageSquare,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

function statusLabel(status: StoredFile["status"]): string {
  return status === "ready" ? "Ready to analyse" : status.replace(/_/g, " ");
}

export default function FilesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [expandedFileId, setExpandedFileId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    async function load() {
      try {
        const [me, chatList, fileList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.listFiles(),
        ]);
        setUser(me);
        setChats(chatList);
        setFiles(fileList);
        if (fileList.length > 0) {
          setExpandedFileId(fileList[0].id);
        }
      } catch {
        router.push("/login");
      }
    }
    load();
  }, [router]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setUploading(true);
    try {
      const uploaded = await api.uploadFile(selected);
      setFiles((prev) => [uploaded, ...prev]);
      setExpandedFileId(uploaded.id);
    } catch (err: any) {
      alert(err.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleStartAnalysis = async (fileId: string) => {
    try {
      const newSession = await api.createChat("Dataset Analysis");
      router.push(`/chat/${newSession.id}`);
    } catch {}
  };

  const handleDeleteFile = async (file: StoredFile) => {
    if (!window.confirm(`Delete "${file.original_name}"? This cannot be undone.`)) return;
    setDeletingFileId(file.id);
    try {
      await api.deleteFile(file.id);
      setFiles((prev) => prev.filter((item) => item.id !== file.id));
      if (expandedFileId === file.id) setExpandedFileId(null);
    } catch (err) {
      alert(err instanceof Error ? err.message : "Dataset deletion failed");
    } finally {
      setDeletingFileId(null);
    }
  };

  return (
    <div className="app-main flex h-screen min-h-0">
      <Sidebar
        user={user}
        chats={chats}
        onNewChat={() => router.push("/chat")}
      />

      <main className="app-main flex min-w-0 flex-1 flex-col overflow-y-auto px-5 py-6 sm:px-8 sm:py-8">
        <div className="page-header flex flex-wrap items-end justify-between gap-4 border-b pb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] text-white">
              Datasets
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Upload a CSV or Excel file to profile its schema before asking questions in chat.
            </p>
          </div>

          <div>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".csv,.xlsx,.xls"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="accent-action flex items-center gap-2 rounded-lg px-4 py-2.5 text-xs font-semibold text-white transition disabled:opacity-50"
            >
              <UploadCloud className="h-4 w-4" />
              {uploading ? "Profiling dataset…" : "Upload dataset"}
            </button>
          </div>
        </div>

        {/* Datasets List */}
        <div className="mx-auto mt-7 w-full max-w-[1180px] space-y-4">
          {files.length === 0 ? (
            <div className="surface-panel rounded-lg border border-dashed p-8 sm:p-12">
              <FileSpreadsheet className="h-5 w-5 text-[var(--accent)]" />
              <h3 className="mt-4 text-lg font-semibold text-white">
                Start with a dataset
              </h3>
              <p className="mt-2 max-w-md text-sm leading-6 text-slate-400">
                Upload a CSV or Excel spreadsheet. We’ll show the row count, fields, nulls, and sample values before analysis.
              </p>
              <button onClick={() => fileInputRef.current?.click()} className="accent-action mt-6 rounded-md px-4 py-2.5 text-sm font-semibold">Upload your first dataset</button>
            </div>
          ) : (
            files.map((file) => {
              const isExpanded = expandedFileId === file.id;
              const profile = file.schema_profile;
              return (
                <div
                  key={file.id}
                  className="surface-panel rounded-lg border p-5 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex min-w-0 items-start gap-3">
                      <FileSpreadsheet className="mt-0.5 h-5 w-5 shrink-0 text-[var(--accent)]" />
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-white">
                          {file.original_name}
                        </h3>
                        <p className="text-[11px] text-slate-400">
                          {(file.size_bytes / 1024).toFixed(1)} KB · {profile?.row_count ?? 0} rows · {profile?.column_count ?? 0} columns
                        </p>
                        <p className={`mt-1 text-xs ${file.status === "error" || profile?.error ? "text-red-300" : "text-emerald-300"}`}>
                          {file.status === "error" || profile?.error ? "Needs attention" : statusLabel(file.status)}
                        </p>
                        {file.status === "error" || profile?.error ? (
                          <p className="mt-1 text-[11px] text-red-400">
                            Profiling error: {String(profile?.error || "Failed to parse file")}
                          </p>
                        ) : null}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleStartAnalysis(file.id)}
                        className="flex items-center gap-1.5 rounded-md border border-white/15 px-3 py-2 text-xs font-medium text-slate-200 transition hover:border-[var(--accent)]/60 hover:text-white"
                      >
                        <MessageSquare className="h-3.5 w-3.5" />
                        Analyze in Chat
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteFile(file)}
                        disabled={deletingFileId === file.id}
                        aria-label={`Delete ${file.original_name}`}
                        title={`Delete ${file.original_name}`}
                        className="rounded-md p-2 text-slate-400 transition hover:bg-red-950/50 hover:text-red-300 disabled:cursor-wait disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setExpandedFileId(isExpanded ? null : file.id)}
                        aria-label={`${isExpanded ? "Collapse" : "Expand"} ${file.original_name} profile`}
                        className="rounded-md p-2 text-slate-400 hover:bg-slate-800 hover:text-white"
                      >
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Profile */}
                  {isExpanded && profile && (
                    <div className="mt-5 border-t border-slate-800 pt-4">
                      <div className="mb-3 flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-300">
                          Inferred Schema Profile ({profile.columns?.length || 0} fields)
                        </span>
                        {profile.sheets && profile.sheets.length > 0 && (
                          <span className="text-[11px] text-slate-500">
                            Sheets: {profile.sheets.join(", ")}
                          </span>
                        )}
                      </div>

                      <div className="data-table overflow-x-auto rounded-lg border border-slate-800/80">
                        <table className="w-full text-left text-xs">
                          <thead className="text-slate-300">
                            <tr>
                              <th className="px-3 py-2 font-semibold">Column Name</th>
                              <th className="px-3 py-2 font-semibold">Inferred Type</th>
                              <th className="px-3 py-2 font-semibold">Null Count</th>
                              <th className="px-3 py-2 font-semibold">Unique Values</th>
                              <th className="px-3 py-2 font-semibold">Sample Values</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 text-slate-300">
                            {profile.columns?.map((col) => (
                              <tr key={col.name} className="hover:bg-slate-800/30">
                                <td className="px-3 py-2 font-medium text-white">{col.name}</td>
                                <td className="px-3 py-2 font-mono text-[var(--accent)]">{col.inferred_type}</td>
                                <td className="px-3 py-2 text-right tabular-nums text-slate-400">{col.null_count}</td>
                                <td className="px-3 py-2 text-right tabular-nums text-slate-400">{col.unique_count}</td>
                                <td
                                  className="max-w-[320px] truncate px-3 py-2 font-mono text-[11px] text-slate-400"
                                  title={col.sample_values?.slice(0, 3).join(", ") || "No sample values"}
                                >
                                  {col.sample_values?.slice(0, 3).join(", ") || "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </main>
    </div>
  );
}
