"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import {
  ArrowUp,
  Plus,
  X,
  FileSpreadsheet,
  Check,
  Search,
  Loader2,
  StopCircle,
} from "lucide-react";
import { StoredFile } from "@/lib/api";

interface ComposerProps {
  files: StoredFile[];
  selectedFileIds: string[];
  onSelectFileIds: (ids: string[]) => void;
  onSend: (content: string, fileIds: string[]) => void;
  disabled?: boolean;
  onStop?: () => void;
  placeholder?: string;
}

export default function Composer({
  files,
  selectedFileIds,
  onSelectFileIds,
  onSend,
  disabled = false,
  onStop,
  placeholder = "Ask Universal Analyst or evaluate policy compliance...",
}: ComposerProps) {
  const [text, setText] = useState("");
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      const nextHeight = Math.min(textareaRef.current.scrollHeight, 180);
      textareaRef.current.style.height = `${Math.max(nextHeight, 44)}px`;
    }
  }, [text]);

  // Click outside to close picker
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowFilePicker(false);
      }
    }
    if (showFilePicker) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showFilePicker]);

  const handleSubmit = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim(), selectedFileIds);
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "44px";
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const toggleFile = (id: string) => {
    if (selectedFileIds.includes(id)) {
      onSelectFileIds(selectedFileIds.filter((fid) => fid !== id));
    } else {
      onSelectFileIds([...selectedFileIds, id]);
    }
  };

  const removeFile = (id: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    onSelectFileIds(selectedFileIds.filter((fid) => fid !== id));
  };

  const filteredFiles = files.filter((f) =>
    f.original_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="relative w-full max-w-4xl mx-auto px-4 pb-4">
      {/* Attached Files Tray */}
      {selectedFileIds.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-2 animate-in fade-in slide-in-from-bottom-2 duration-150">
          {selectedFileIds.map((fid) => {
            const file = files.find((f) => f.id === fid);
            const isXlsx = file?.original_name.toLowerCase().endsWith(".xlsx") || file?.original_name.toLowerCase().endsWith(".xls");
            const extLabel = isXlsx ? "XLSX" : "CSV";
            const rowCount = file?.schema_profile?.row_count;

            return (
              <div
                key={fid}
                className="group flex items-center gap-2.5 rounded-xl border border-synapse-border bg-synapse-raised px-3 py-2 text-xs text-synapse-text shadow-subtle hover:border-synapse-border-strong transition-all"
              >
                <div
                  className={`flex h-6 px-1.5 items-center justify-center rounded text-[10px] font-bold tracking-wider ${
                    isXlsx
                      ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/50"
                      : "bg-blue-950/80 text-blue-300 border border-blue-800/50"
                  }`}
                >
                  {extLabel}
                </div>
                <div className="flex flex-col min-w-0">
                  <span className="font-medium truncate max-w-[200px]">
                    {file?.original_name || fid}
                  </span>
                  <span className="text-[10px] text-synapse-muted">
                    {rowCount !== undefined ? `${rowCount.toLocaleString()} rows • ` : ""}Ready
                  </span>
                </div>
                <button
                  type="button"
                  onClick={(e) => removeFile(fid, e)}
                  title="Remove attachment"
                  aria-label={`Remove ${file?.original_name || fid}`}
                  className="rounded-full p-1 text-synapse-muted hover:text-synapse-text hover:bg-synapse-hover transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Main Composer Box */}
      <div className="relative rounded-2xl border border-synapse-border-strong bg-synapse-raised/95 shadow-composer backdrop-blur-xl transition-all focus-within:border-synapse-accent/60 focus-within:ring-1 focus-within:ring-synapse-accent/30">
        {/* Attachment Picker Popover */}
        {showFilePicker && (
          <div
            ref={pickerRef}
            className="absolute bottom-full left-0 mb-3 w-88 max-w-[95vw] rounded-2xl border border-synapse-border-strong bg-synapse-raised p-3 shadow-2xl backdrop-blur-2xl z-30 animate-in fade-in slide-in-from-bottom-2 duration-150"
          >
            <div className="flex items-center justify-between pb-2.5 border-b border-synapse-border">
              <span className="text-xs font-semibold text-synapse-text">
                Attach Datasets for Analysis
              </span>
              <button
                type="button"
                onClick={() => setShowFilePicker(false)}
                className="rounded-lg p-1 text-synapse-muted hover:text-synapse-text hover:bg-synapse-hover"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Search Input */}
            <div className="relative mt-2.5 mb-2">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-synapse-muted" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search datasets..."
                className="w-full rounded-xl border border-synapse-border bg-synapse-surface py-1.5 pl-8 pr-3 text-xs text-synapse-text placeholder-synapse-muted focus:border-synapse-accent focus:outline-none"
              />
            </div>

            <div className="max-h-52 overflow-y-auto space-y-1 pr-1">
              {filteredFiles.length === 0 ? (
                <div className="py-6 text-center text-xs text-synapse-muted">
                  No matching datasets found.
                </div>
              ) : (
                filteredFiles.map((f) => {
                  const isSelected = selectedFileIds.includes(f.id);
                  const isXlsx = f.original_name.toLowerCase().endsWith(".xlsx") || f.original_name.toLowerCase().endsWith(".xls");
                  const extLabel = isXlsx ? "XLSX" : "CSV";

                  return (
                    <button
                      key={f.id}
                      type="button"
                      onClick={() => toggleFile(f.id)}
                      className={`flex w-full items-center justify-between rounded-xl p-2 text-left text-xs transition-colors border ${
                        isSelected
                          ? "bg-synapse-hover text-synapse-text border-synapse-accent/40"
                          : "text-synapse-secondary hover:bg-synapse-hover hover:text-synapse-text border-transparent"
                      }`}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <span
                          className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                            isXlsx
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/40"
                              : "bg-blue-950/80 text-blue-300 border border-blue-800/40"
                          }`}
                        >
                          {extLabel}
                        </span>
                        <div className="truncate">
                          <div className="truncate font-medium text-synapse-text">
                            {f.original_name}
                          </div>
                          <div className="text-[10px] text-synapse-muted">
                            {f.schema_profile?.row_count !== undefined
                              ? `${f.schema_profile.row_count.toLocaleString()} rows`
                              : "Dataset"}
                          </div>
                        </div>
                      </div>

                      <div
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                          isSelected
                            ? "border-synapse-accent bg-synapse-accent text-white"
                            : "border-synapse-border bg-synapse-surface text-transparent"
                        }`}
                      >
                        <Check className="h-3 w-3" />
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        )}

        {/* Input Area */}
        <div className="px-4 pt-3 pb-1">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="w-full resize-none bg-transparent text-sm text-synapse-text placeholder-synapse-muted focus:outline-none disabled:opacity-50 leading-relaxed font-sans"
          />
        </div>

        {/* Bottom Toolbar */}
        <div className="flex items-center justify-between px-3 py-2 border-t border-synapse-border-subtle">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowFilePicker(!showFilePicker)}
              className="flex items-center gap-1.5 rounded-xl border border-synapse-border bg-synapse-surface hover:bg-synapse-hover px-2.5 py-1.5 text-xs font-medium text-synapse-secondary hover:text-synapse-text transition-colors shadow-subtle"
            >
              <Plus className="h-3.5 w-3.5 text-synapse-accent" />
              <span>Attach</span>
            </button>

            {selectedFileIds.length > 0 && (
              <span className="text-[11px] text-synapse-muted font-mono hidden sm:inline">
                {selectedFileIds.length} attached
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] text-synapse-faint hidden sm:inline font-mono">
              ↵ Send • ⇧↵ Line
            </span>

            {disabled && onStop ? (
              <button
                type="button"
                onClick={onStop}
                title="Stop generation"
                aria-label="Stop generation"
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-synapse-surface border border-synapse-border text-synapse-danger hover:bg-synapse-hover transition-colors"
              >
                <StopCircle className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={disabled || !text.trim()}
                title="Send query"
                aria-label="Send query"
                className="flex h-8 w-8 items-center justify-center rounded-xl bg-synapse-accent text-white shadow-subtle hover:bg-synapse-accent-hover transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                {disabled ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <ArrowUp className="h-4 w-4 stroke-[2.5]" />
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
