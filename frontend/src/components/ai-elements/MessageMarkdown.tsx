"use client";

import { memo, type ReactNode } from "react";
import { CodeBlock } from "@/components/ai-elements/CodeBlock";
import { cn } from "@/lib/cn";

/* ------------------------------------------------------------------ */
/* Inline markdown                                                     */
/* ------------------------------------------------------------------ */

const INLINE_PATTERN = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`|~~[^~\n]+~~|\[[^\]]+\]\([^)\s]+\))/g;

function safeHref(raw: string): string | null {
  const value = raw.trim();
  if (/^https?:\/\//i.test(value) || value.startsWith("/") || value.startsWith("#")) return value;
  return null;
}

export function inlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(INLINE_PATTERN).filter((part) => part !== undefined && part !== "");
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;

    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("__") && part.endsWith("__") && part.length > 4) {
      return <strong key={key} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("~~") && part.endsWith("~~") && part.length > 4) {
      return <span key={key} className="text-slate-400 line-through">{part.slice(2, -2)}</span>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={key} className="italic text-slate-200">{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("_") && part.endsWith("_") && part.length > 2) {
      return <em key={key} className="italic text-slate-200">{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={key} className="rounded bg-slate-800/80 px-1 py-0.5 font-mono text-[0.92em] text-[var(--accent-strong)]">
          {part.slice(1, -1)}
        </code>
      );
    }

    const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (link) {
      const href = safeHref(link[2]);
      if (!href) return <span key={key}>{link[1]}</span>;
      const external = /^https?:\/\//i.test(href);
      return (
        <a
          key={key}
          href={href}
          target={external ? "_blank" : undefined}
          rel={external ? "noreferrer noopener" : undefined}
          className="text-[var(--accent)] underline decoration-white/30 underline-offset-2 hover:text-[var(--accent-strong)] hover:decoration-white"
        >
          {link[1]}
        </a>
      );
    }

    return <span key={key}>{part}</span>;
  });
}

/* ------------------------------------------------------------------ */
/* Block parsing                                                       */
/* ------------------------------------------------------------------ */

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const values = cells(line);
  return values.length > 0 && values.every((value) => /^:?-{3,}:?$/.test(value));
}

function isAlignmentSeparator(line: string): boolean {
  return isTableSeparator(line);
}

type Block =
  | { type: "paragraph"; lines: string[] }
  | { type: "heading"; level: number; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "code"; language: string; code: string }
  | { type: "quote"; lines: string[] }
  | { type: "table"; header: string[]; rows: string[][]; align: ("left" | "right" | "center")[] }
  | { type: "hr" };

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];

  const flush = () => {
    if (paragraph.length) {
      blocks.push({ type: "paragraph", lines: paragraph });
      paragraph = [];
    }
  };

  for (let index = 0; index < lines.length; ) {
    const line = lines[index];

    // Fenced code (also handles a fence still streaming in)
    const fence = line.match(/^\s*```([\w+-]*)\s*$/);
    if (fence) {
      flush();
      const language = fence[1] || "";
      const body: string[] = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1; // skip closing fence (if present)
      blocks.push({ type: "code", language, code: body.join("\n") });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      flush();
      blocks.push({ type: "heading", level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flush();
      blocks.push({ type: "hr" });
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flush();
      const quote: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", lines: quote });
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isAlignmentSeparator(lines[index + 1])) {
      flush();
      const header = cells(line);
      const align = cells(lines[index + 1]).map((marker) =>
        marker.startsWith(":") && marker.endsWith(":")
          ? "center"
          : marker.endsWith(":")
            ? "right"
            : "left",
      );
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push({ type: "table", header, rows, align });
      continue;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flush();
      const isOrdered = Boolean(ordered);
      const items: string[] = [];
      const pattern = isOrdered ? /^\s*\d+[.)]\s+(.+)$/ : /^\s*[-*+]\s+(.+)$/;
      while (index < lines.length) {
        const match = lines[index].match(pattern);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ type: "list", ordered: isOrdered, items });
      continue;
    }

    if (!line.trim()) {
      flush();
      index += 1;
      continue;
    }

    paragraph.push(line);
    index += 1;
  }

  flush();
  return blocks;
}

/* ------------------------------------------------------------------ */
/* Renderer                                                            */
/* ------------------------------------------------------------------ */

function MarkdownMessageImpl({
  content,
  streaming = false,
  className,
}: {
  content: string;
  streaming?: boolean;
  className?: string;
}) {
  const blocks = parseBlocks(content || "");

  return (
    <div className={cn("text-[13.5px] leading-7 text-slate-200", className)}>
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;
        const isLast = index === blocks.length - 1;

        switch (block.type) {
          case "heading": {
            const size =
              block.level <= 1
                ? "text-[15px] mt-5 mb-2"
                : block.level === 2
                  ? "text-[14px] mt-4 mb-1.5"
                  : "text-[13px] mt-3 mb-1";
            return (
              <div key={key} className={cn("font-semibold text-white first:mt-0", size)}>
                {inlineMarkdown(block.text, key)}
              </div>
            );
          }
          case "paragraph":
            return (
              <p key={key} className="my-2 whitespace-pre-wrap first:mt-0 last:mb-0">
                {block.lines.flatMap((line, lineIndex) => [
                  ...(lineIndex ? [<br key={`${key}-br-${lineIndex}`} />] : []),
                  ...inlineMarkdown(line, `${key}-${lineIndex}`),
                ])}
                {streaming && isLast ? <Caret /> : null}
              </p>
            );
          case "list": {
            const ListTag = block.ordered ? "ol" : "ul";
            return (
              <ListTag
                key={key}
                className={cn(
                  "my-2 space-y-1 pl-5 first:mt-0",
                  block.ordered ? "list-decimal" : "list-disc",
                  "marker:text-slate-500",
                )}
              >
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`} className="pl-0.5">
                    {inlineMarkdown(item, `${key}-${itemIndex}`)}
                  </li>
                ))}
              </ListTag>
            );
          }
          case "code":
            return <CodeBlock key={key} code={block.code} language={block.language} />;
          case "quote":
            return (
              <blockquote
                key={key}
                className="my-3 border-l-2 border-white/25 bg-slate-900/40 py-1.5 pl-3 pr-2 text-slate-300"
              >
                {block.lines.map((line, lineIndex) => (
                  <p key={`${key}-${lineIndex}`} className="my-0.5 whitespace-pre-wrap">
                    {inlineMarkdown(line, `${key}-${lineIndex}`)}
                  </p>
                ))}
              </blockquote>
            );
          case "table":
            return (
              <div key={key} className="my-3 overflow-x-auto rounded-lg border border-slate-800">
                <table className="w-full border-collapse text-left text-[12px]">
                  <thead className="bg-slate-900/80 text-slate-300">
                    <tr>
                      {block.header.map((cell, cellIndex) => (
                        <th
                          key={cellIndex}
                          className={cn(
                            "whitespace-nowrap px-3 py-2 font-medium",
                            block.align[cellIndex] === "right" && "text-right",
                            block.align[cellIndex] === "center" && "text-center",
                          )}
                        >
                          {inlineMarkdown(cell, `${key}-h-${cellIndex}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {block.rows.map((row, rowIndex) => (
                      <tr key={rowIndex} className="hover:bg-slate-900/40">
                        {block.header.map((_, cellIndex) => {
                          const value = row[cellIndex] ?? "";
                          const numeric = /^-?[\d,]+(\.\d+)?$/.test(value.trim());
                          const align = block.align[cellIndex];
                          return (
                            <td
                              key={cellIndex}
                              className={cn(
                                "px-3 py-1.5 text-slate-300",
                                numeric && "tabular-nums",
                                align === "right" && "text-right",
                                align === "center" && "text-center",
                              )}
                            >
                              {inlineMarkdown(value, `${key}-${rowIndex}-${cellIndex}`)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "hr":
            return <hr key={key} className="my-4 border-slate-800" />;
          default:
            return null;
        }
      })}
      {streaming && blocks.length === 0 ? (
        <p className="text-slate-400">
          <Caret />
        </p>
      ) : null}
    </div>
  );
}

function Caret() {
  return (
    <span
      aria-hidden
      className="ml-0.5 inline-block h-[1.05em] w-[2px] translate-y-[2px] animate-pulse rounded-full bg-[var(--accent)] align-baseline"
    />
  );
}

/**
 * Streaming-safe markdown. Re-parses only when its own content changes, so a
 * token update never re-renders the rest of the page.
 */
export const MessageMarkdown = memo(MarkdownMessageImpl);
export default MessageMarkdown;
