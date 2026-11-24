"use client";

import { useState } from "react";
import { Send, Paperclip, X, FileSpreadsheet } from "lucide-react";
import { StoredFile } from "@/lib/api";

interface ComposerProps {
  files: StoredFile[];
  selectedFileIds: string[];
  onSelectFileIds: (ids: string[]) => void;
  onSend: (content: string, fileIds: string[]) => void;
  disabled?: boolean;
}

export default function Composer({
  files,
  selectedFileIds,
  onSelectFileIds,
  onSend,
  disabled = false,
}: ComposerProps) {
  const [text, setText] = useState("");
  const [showFilePicker, setShowFilePicker] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    onSend(text.trim(), selectedFileIds);
    setText("");
  };

  const toggleFile = (id: string) => {
    if (selectedFileIds.includes(id)) {
      onSelectFileIds(selectedFileIds.filter((fid) => fid !== id));
    } else {
      onSelectFileIds([...selectedFileIds, id]);
    }
  };

  return (
    <div className="relative border-t border-slate-800 bg-slate-900/95 p-4 backdrop-blur-md">
      {/* File Drawer Popover */}
      {showFilePicker && (
        <div className="absolute bottom-full left-4 mb-2 w-80 rounded-xl border border-slate-700 bg-slate-800/95 p-3 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between pb-2 border-b border-slate-700">
            <span className="text-xs font-semibold text-slate-200">
              Attach Datasets to Query
            </span>
            <button
              onClick={() => setShowFilePicker(false)}
              className="text-slate-400 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-2 max-h-48 overflow-y-auto space-y-1">
            {files.length === 0 ? (
              <div className="py-3 text-center text-xs text-slate-400">
                No datasets uploaded yet. Visit Datasets tab.
              </div>
            ) : (
              files.map((f) => {
                const isSelected = selectedFileIds.includes(f.id);
                return (
                  <button
                    key={f.id}
                    onClick={() => toggleFile(f.id)}
                    className={`flex w-full items-center justify-between rounded-lg p-2 text-left text-xs transition ${
                      isSelected
                        ? "bg-indigo-950/70 text-indigo-300 ring-1 ring-indigo-500/40"
                        : "hover:bg-slate-700/50 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-indigo-400" />
                      <span className="truncate">{f.original_name}</span>
                    </div>
                    {f.schema_profile?.row_count !== undefined && (
                      <span className="text-[10px] text-slate-400 shrink-0">
                        {f.schema_profile.row_count} rows
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Selected Files Badges */}
      {selectedFileIds.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {selectedFileIds.map((fid) => {
            const fileObj = files.find((f) => f.id === fid);
            return (
              <span
                key={fid}
                className="flex items-center gap-1.5 rounded-md bg-indigo-950/80 px-2 py-0.5 text-xs text-indigo-300 border border-indigo-800/40"
              >
                <FileSpreadsheet className="h-3 w-3 text-indigo-400" />
                <span className="max-w-[150px] truncate">
                  {fileObj ? fileObj.original_name : fid}
                </span>
                <button
                  type="button"
                  onClick={() => toggleFile(fid)}
                  className="hover:text-red-400"
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Form Input */}
      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setShowFilePicker(!showFilePicker)}
          title="Attach dataset file"
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-700 bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white transition"
        >
          <Paperclip className="h-4 w-4" />
        </button>

        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask a question about your data or evaluate policy compliance..."
          disabled={disabled}
          className="flex-1 rounded-xl border border-slate-700 bg-slate-800/90 px-4 py-2.5 text-xs text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />

        <button
          type="submit"
          disabled={disabled || !text.trim()}
          className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/30 transition hover:bg-indigo-500 disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}
