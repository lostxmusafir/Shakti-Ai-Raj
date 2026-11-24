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
  Database,
  Layers,
  Table,
  CheckCircle2,
  ArrowRight,
  HardDrive,
} from "lucide-react";

export default function FilesPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [files, setFiles] = useState<StoredFile[]>([]);
  const [expandedFileId, setExpandedFileId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [me, chatList, fileList] = await Promise.all([
          api.getMe(),
          api.listChats(),
          api.listFiles(),
        ]);
        if (cancelled) return;
        setUser(me);
        setChats(chatList);
        setFiles(fileList);
        if (fileList.length > 0) {
          setExpandedFileId(fileList[0].id);
        }
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

  const handleStartAnalysis = async (fileId: string, fileName: string) => {
    try {
      const newSession = await api.createChat(`Analysis: ${fileName}`);
      if (typeof window !== "undefined") {
        sessionStorage.setItem(
          `pending_prompt_${newSession.id}`,
          JSON.stringify({
            content: `Tell me about the dataset "${fileName}" and summarize key distributions`,
            fileIds: [fileId],
          })
        );
      }
      router.push(`/chat/${newSession.id}`);
    } catch (err: any) {
      alert("Failed to create chat session.");
    }
  };

  const handleDeleteFile = async (fileId: string, name: string) => {
    if (!window.confirm(`Delete ${name}? Stored schema profile will be removed.`)) return;
    try {
      await api.deleteFile(fileId);
      setFiles((prev) => prev.filter((file) => file.id !== fileId));
      setExpandedFileId((current) => (current === fileId ? null : current));
    } catch (err: any) {
      alert(err.message || "Failed to delete file.");
    }
  };

  const totalRows = files.reduce((acc, f) => acc + (f.schema_profile?.row_count || 0), 0);
  const totalCols = files.reduce((acc, f) => acc + (f.schema_profile?.columns?.length || 0), 0);
  const totalSizeBytes = files.reduce((acc, f) => acc + (f.size_bytes || 0), 0);
  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-synapse-bg">
        <div className="flex flex-col items-center gap-3">
          <div className="h-6 w-6 rounded-full border-2 border-synapse-border border-t-synapse-accent animate-spin" />
          <p className="text-xs text-synapse-muted">Loading datasets...</p>
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
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-synapse-border">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-synapse-text">
              Datasets & Schema Profiler
            </h1>
            <p className="mt-1 text-xs text-synapse-secondary">
              Ingest delimited text and Excel datasets (CSV, TXT, XLS/XLSX) for deterministic DuckDB queries and automatic server-side schema profiling.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileUpload}
              accept=".csv,.txt,.xlsx,.xls"
              className="hidden"
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="flex items-center gap-2 rounded-xl bg-synapse-accent hover:bg-synapse-accent-hover px-4 py-2 text-xs font-semibold text-white shadow-subtle transition-colors disabled:opacity-50"
            >
              <UploadCloud className="h-4 w-4" />
              <span>{uploading ? "Profiling Dataset..." : "Upload Dataset"}</span>
            </button>
          </div>
        </div>

        {/* Metric Summary Cards */}
        <div className="mt-6 grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="rounded-xl border border-synapse-border bg-synapse-surface p-3.5 shadow-subtle">
            <div className="flex items-center justify-between text-synapse-muted mb-1">
              <span className="text-[11px] font-medium uppercase tracking-wider">Total Files</span>
              <FileSpreadsheet className="h-4 w-4 text-synapse-accent" />
            </div>
            <div className="text-xl font-bold font-mono text-synapse-text">{files.length}</div>
          </div>

          <div className="rounded-xl border border-synapse-border bg-synapse-surface p-3.5 shadow-subtle">
            <div className="flex items-center justify-between text-synapse-muted mb-1">
              <span className="text-[11px] font-medium uppercase tracking-wider">Total Records</span>
              <Database className="h-4 w-4 text-emerald-400" />
            </div>
            <div className="text-xl font-bold font-mono text-synapse-text">
              {totalRows.toLocaleString()}
            </div>
          </div>

          <div className="rounded-xl border border-synapse-border bg-synapse-surface p-3.5 shadow-subtle">
            <div className="flex items-center justify-between text-synapse-muted mb-1">
              <span className="text-[11px] font-medium uppercase tracking-wider">Profiled Columns</span>
              <Table className="h-4 w-4 text-synapse-warm" />
            </div>
            <div className="text-xl font-bold font-mono text-synapse-text">{totalCols}</div>
          </div>

          <div className="rounded-xl border border-synapse-border bg-synapse-surface p-3.5 shadow-subtle">
            <div className="flex items-center justify-between text-synapse-muted mb-1">
              <span className="text-[11px] font-medium uppercase tracking-wider">Storage Used</span>
              <HardDrive className="h-4 w-4 text-blue-400" />
            </div>
            <div className="text-xl font-bold font-mono text-synapse-text">
              {formatBytes(totalSizeBytes)}
            </div>
          </div>
        </div>

        {/* Datasets List */}
        <div className="mt-8 space-y-4">
          {files.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-synapse-border p-12 text-center bg-synapse-surface/40">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-synapse-raised border border-synapse-border text-synapse-muted mb-3">
                <FileSpreadsheet className="h-6 w-6" />
              </div>
              <h3 className="text-sm font-semibold text-synapse-text">
                No datasets uploaded yet
              </h3>
              <p className="mt-1 text-xs text-synapse-muted max-w-sm">
                Upload a delimited text or Excel file to begin automated schema profiling and deterministic analytical queries.
              </p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="mt-4 flex items-center gap-1.5 rounded-xl border border-synapse-border bg-synapse-raised hover:bg-synapse-hover px-3.5 py-2 text-xs font-medium text-synapse-text transition-colors"
              >
                <UploadCloud className="h-3.5 w-3.5 text-synapse-accent" />
                <span>Upload First Dataset</span>
              </button>
            </div>
          ) : (
            files.map((file) => {
              const isExpanded = expandedFileId === file.id;
              const profile = file.schema_profile;
              const isXlsx =
                file.original_name.toLowerCase().endsWith(".xlsx") ||
                file.original_name.toLowerCase().endsWith(".xls");
              const extLabel = isXlsx ? "XLSX" : "CSV";

              return (
                <div
                  key={file.id}
                  className="rounded-2xl border border-synapse-border bg-synapse-surface shadow-subtle transition-all overflow-hidden"
                >
                  {/* File Row Header */}
                  <div className="flex items-center justify-between p-4 flex-wrap gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold ${
                          isXlsx
                            ? "bg-emerald-950/70 text-emerald-300 border border-emerald-800/40"
                            : "bg-blue-950/70 text-blue-300 border border-blue-800/40"
                        }`}
                      >
                        {extLabel}
                      </div>

                      <div className="truncate">
                        <h3 className="text-sm font-semibold text-synapse-text truncate">
                          {file.original_name}
                        </h3>
                        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-synapse-muted">
                          <span>{formatBytes(file.size_bytes)}</span>
                          <span>•</span>
                          <span>{profile?.row_count !== undefined ? `${profile.row_count.toLocaleString()} rows` : "Ready"}</span>
                          <span>•</span>
                          <span>{profile?.columns?.length || 0} fields</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleStartAnalysis(file.id, file.original_name)}
                        className="flex items-center gap-1.5 rounded-xl border border-synapse-border bg-synapse-raised hover:bg-synapse-hover px-3 py-1.5 text-xs font-medium text-synapse-text transition-colors"
                      >
                        <MessageSquare className="h-3.5 w-3.5 text-synapse-accent" />
                        <span>Analyze in Chat</span>
                      </button>

                      <button
                        onClick={() => handleDeleteFile(file.id, file.original_name)}
                        className="rounded-xl border border-synapse-border p-2 text-synapse-muted hover:text-synapse-danger hover:bg-synapse-raised transition-colors"
                        title="Delete dataset"
                        aria-label="Delete dataset"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>

                      <button
                        onClick={() => setExpandedFileId(isExpanded ? null : file.id)}
                        className="rounded-xl border border-synapse-border p-2 text-synapse-secondary hover:text-synapse-text hover:bg-synapse-raised transition-colors"
                        title={isExpanded ? "Collapse schema" : "Expand schema"}
                      >
                        {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Schema Profiling Drawer */}
                  {isExpanded && profile && (
                    <div className="border-t border-synapse-border bg-synapse-raised/40 p-4 space-y-4 animate-in fade-in duration-150">
                      {profile.sheets && profile.sheets.length > 0 && (
                        <div className="flex items-center gap-2 text-xs text-synapse-secondary">
                          <span className="font-semibold text-synapse-muted">Workbook Sheets:</span>
                          <div className="flex flex-wrap gap-1.5">
                            {profile.sheets.map((sheet) => (
                              <span
                                key={sheet}
                                className="rounded-md bg-synapse-surface border border-synapse-border px-2 py-0.5 text-xs text-synapse-accent font-mono"
                              >
                                {sheet}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Schema Columns Table */}
                      <div className="overflow-x-auto rounded-xl border border-synapse-border bg-synapse-surface">
                        <table className="w-full text-left text-xs">
                          <thead className="border-b border-synapse-border bg-synapse-raised/60 text-synapse-muted">
                            <tr>
                              <th className="px-3.5 py-2 font-medium">Field Name</th>
                              <th className="px-3.5 py-2 font-medium">Inferred Type</th>
                              <th className="px-3.5 py-2 font-medium">Null Values</th>
                              <th className="px-3.5 py-2 font-medium">Unique Values</th>
                              <th className="px-3.5 py-2 font-medium">Sample Values</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-synapse-border/40 font-mono text-synapse-secondary">
                            {profile.columns?.map((col) => (
                              <tr key={col.name} className="hover:bg-synapse-hover/40 transition-colors">
                                <td className="px-3.5 py-2 font-semibold text-synapse-text">
                                  {col.name}
                                </td>
                                <td className="px-3.5 py-2 text-synapse-accent">
                                  {col.inferred_type}
                                </td>
                                <td className="px-3.5 py-2">
                                  {col.null_count > 0 ? (
                                    <span className="text-amber-400">{col.null_count} nulls</span>
                                  ) : (
                                    <span className="text-synapse-faint">0 nulls</span>
                                  )}
                                </td>
                                <td className="px-3.5 py-2 text-synapse-secondary">
                                  {col.unique_count !== undefined ? col.unique_count : "—"}
                                </td>
                                <td className="px-3.5 py-2 font-sans">
                                  <div className="flex flex-wrap gap-1">
                                    {col.sample_values?.slice(0, 3).map((val, vIdx) => (
                                      <span
                                        key={vIdx}
                                        className="rounded bg-synapse-raised border border-synapse-border px-1.5 py-0.5 text-[10px] text-synapse-muted truncate max-w-[120px]"
                                      >
                                        {String(val)}
                                      </span>
                                    ))}
                                  </div>
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
