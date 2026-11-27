"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Check, FileSpreadsheet, Paperclip, X } from "lucide-react";
import { StoredFile } from "@/lib/api";
import Attachments from "@/components/ai-elements/Attachments";
import { cn } from "@/lib/cn";
import { formatNumber } from "@/lib/format";

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = textareaRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`;
  }, [text]);

  useEffect(() => {
    if (!showFilePicker) return;
    const onPointerDown = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setShowFilePicker(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [showFilePicker]);

  const submit = () => {
    const value = text.trim();
    if (!value || disabled) return;
    onSend(value, selectedFileIds);
    setText("");
  };

  const toggleFile = (id: string) => {
    onSelectFileIds(
      selectedFileIds.includes(id) ? selectedFileIds.filter((fileId) => fileId !== id) : [...selectedFileIds, id],
    );
  };

  const selected = selectedFileIds.map((id) => {
    const file = files.find((item) => item.id === id);
    return {
      id,
      name: file?.original_name || "Dataset",
      rows: file?.schema_profile?.row_count ?? null,
      state: file?.status ?? null,
    };
  });

  return (
    <div className="border-t border-slate-800/80 bg-slate-950/80">
      <div className="mx-auto w-full max-w-3xl px-5 py-3 sm:px-6">
        {selected.length ? (
          <Attachments items={selected} onRemove={toggleFile} className="mb-2" />
        ) : null}

        <div className="relative">
          {showFilePicker ? (
            <div
              ref={pickerRef}
              className="absolute bottom-full left-0 z-20 mb-2 w-[min(20rem,90vw)] overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-xl shadow-black/40"
            >
              <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
                <span className="text-[11px] font-medium text-slate-300">Attach datasets</span>
                <button
                  type="button"
                  onClick={() => setShowFilePicker(false)}
                  className="rounded p-0.5 text-slate-500 hover:text-slate-200"
                  aria-label="Close dataset picker"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="max-h-56 overflow-y-auto p-1">
                {files.length === 0 ? (
                  <div className="px-3 py-6 text-center text-[11.5px] text-slate-500">
                    No datasets yet. Upload one in the Datasets tab.
                  </div>
                ) : (
                  files.map((file) => {
                    const isSelected = selectedFileIds.includes(file.id);
                    return (
                      <button
                        key={file.id}
                        type="button"
                        onClick={() => toggleFile(file.id)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11.5px] transition",
                          isSelected ? "bg-white/[0.05] text-[var(--accent-strong)]" : "text-slate-300 hover:bg-slate-800/70",
                        )}
                      >
                        <FileSpreadsheet className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" />
                        <span className="min-w-0 flex-1 truncate">{file.original_name}</span>
                        {file.schema_profile?.row_count !== undefined ? (
                          <span className="shrink-0 text-[10px] text-slate-500">
                            {formatNumber(file.schema_profile.row_count)} rows
                          </span>
                        ) : null}
                        {isSelected ? <Check className="h-3.5 w-3.5 shrink-0 text-[var(--accent)]" /> : null}
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          ) : null}

          <div className="flex items-end gap-2 rounded-2xl border border-slate-800 bg-slate-900/70 px-2 py-2 focus-within:border-slate-700 focus-within:ring-1 focus-within:ring-white/20">
            <button
              type="button"
              onClick={() => setShowFilePicker((value) => !value)}
              aria-label="Attach dataset"
              title="Attach dataset"
              className={cn(
                "mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-800 hover:text-slate-200",
                showFilePicker && "bg-slate-800 text-slate-200",
              )}
            >
              <Paperclip className="h-4 w-4" />
            </button>

            <textarea
              ref={textareaRef}
              value={text}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder="Ask a question about your data…"
              disabled={disabled}
              className="max-h-40 min-h-[2rem] flex-1 resize-none bg-transparent py-1.5 text-[13.5px] leading-6 text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-60"
            />

            <button
              type="button"
              onClick={submit}
              disabled={disabled || !text.trim()}
              aria-label="Send message"
              className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--primary)] text-[var(--primary-ink)] transition hover:bg-[var(--accent)] disabled:cursor-not-allowed disabled:bg-slate-800 disabled:text-slate-500"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="mt-1.5 flex items-center justify-between px-1 text-[10.5px] text-slate-600">
          <span>Enter to send · Shift+Enter for a new line</span>
          {selected.length ? <span>{selected.length} dataset{selected.length > 1 ? "s" : ""} attached</span> : null}
        </div>
      </div>
    </div>
  );
}
