"use client";

import { ElementType, ReactNode } from "react";

function inlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  // Regex matches bold, italic, inline code, and links
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={key} className="font-semibold text-synapse-text">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return (
        <em key={key} className="italic text-synapse-secondary">
          {part.slice(1, -1)}
        </em>
      );
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code
          key={key}
          className="rounded-md bg-synapse-raised px-1.5 py-0.5 font-mono text-[11px] text-synapse-accent border border-synapse-border"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a
          key={key}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-synapse-accent hover:underline"
        >
          {linkMatch[1]}
        </a>
      );
    }
    return <span key={key}>{part}</span>;
  });
}

function cells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const values = cells(line);
  return values.length > 0 && values.every((value) => /^:?-{3,}:?$/.test(value));
}

export default function MarkdownMessage({ content }: { content: string }) {
  if (!content) return null;

  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="whitespace-pre-wrap leading-relaxed text-synapse-secondary text-xs sm:text-sm">
        {paragraph.flatMap((line, index) => [
          ...(index ? [<br key={`br-${blocks.length}-${index}`} />] : []),
          ...inlineMarkdown(line, `p-${blocks.length}-${index}`),
        ])}
      </p>
    );
    paragraph = [];
  };

  for (let index = 0; index < lines.length;) {
    const line = lines[index];

    // Fenced Code Block
    if (line.trim().startsWith("```")) {
      flushParagraph();
      const codeLines: string[] = [];
      const lang = line.trim().slice(3).trim();
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push(
        <div key={`code-${index}`} className="my-3 overflow-hidden rounded-xl border border-synapse-border bg-synapse-surface">
          {lang && (
            <div className="border-b border-synapse-border px-3 py-1.5 text-[10px] font-mono uppercase text-synapse-muted bg-synapse-raised/50">
              {lang}
            </div>
          )}
          <pre className="overflow-x-auto p-3.5 font-mono text-xs text-synapse-text leading-relaxed">
            <code>{codeLines.join("\n")}</code>
          </pre>
        </div>
      );
      index += 1;
      continue;
    }

    // Heading
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      const Tag = `h${level}` as ElementType;
      const sizeClasses =
        level === 1
          ? "text-base font-bold text-synapse-text mt-4 mb-2 first:mt-0"
          : level === 2
          ? "text-sm font-semibold text-synapse-text mt-3.5 mb-2 first:mt-0"
          : "text-xs font-semibold text-synapse-text uppercase tracking-wide mt-3 mb-1.5 first:mt-0";

      blocks.push(
        <Tag key={`h-${index}`} className={sizeClasses}>
          {inlineMarkdown(heading[2], `h-${index}`)}
        </Tag>
      );
      index += 1;
      continue;
    }

    // Horizontal Rule
    if (/^---+$|^\*\*\*+$/.test(line.trim())) {
      flushParagraph();
      blocks.push(<hr key={`hr-${index}`} className="my-4 border-synapse-border" />);
      index += 1;
      continue;
    }

    // Table
    if (index + 1 < lines.length && line.includes("|") && isTableSeparator(lines[index + 1])) {
      flushParagraph();
      const header = cells(line);
      const tableRows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        tableRows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div key={`table-${index}`} className="my-3 overflow-x-auto rounded-xl border border-synapse-border bg-synapse-surface shadow-subtle">
          <table className="min-w-full text-left text-xs">
            <thead className="border-b border-synapse-border bg-synapse-raised/80 text-synapse-text font-medium">
              <tr>
                {header.map((cell, cellIndex) => (
                  <th key={cellIndex} className="px-3.5 py-2">
                    {inlineMarkdown(cell, `th-${index}-${cellIndex}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-synapse-border/60 font-mono text-synapse-secondary">
              {tableRows.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-synapse-hover transition-colors">
                  {header.map((_, cellIndex) => (
                    <td key={cellIndex} className="px-3.5 py-2 align-top text-xs">
                      {inlineMarkdown(row[cellIndex] || "", `td-${index}-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    // Lists
    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const orderedList = Boolean(ordered);
      const items: string[] = [];
      while (index < lines.length) {
        const match = lines[index].match(orderedList ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*]\s+(.+)$/);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      const ListTag = orderedList ? "ol" : "ul";
      blocks.push(
        <ListTag
          key={`list-${index}`}
          className={`${orderedList ? "list-decimal" : "list-disc"} mb-2.5 ml-5 space-y-1 text-xs sm:text-sm text-synapse-secondary leading-relaxed`}
        >
          {items.map((item, itemIndex) => (
            <li key={itemIndex}>{inlineMarkdown(item, `li-${index}-${itemIndex}`)}</li>
          ))}
        </ListTag>
      );
      continue;
    }

    // Normal paragraph line
    if (!line.trim()) {
      flushParagraph();
    } else {
      paragraph.push(line);
    }
    index += 1;
  }
  flushParagraph();

  return <div className="space-y-2 leading-relaxed text-synapse-text">{blocks}</div>;
}
