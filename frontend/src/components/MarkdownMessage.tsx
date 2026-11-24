"use client";

import { ElementType, ReactNode } from "react";

function inlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g);
  return parts.map((part, index) => {
    const key = `${keyPrefix}-${index}`;
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={key}>{part.slice(1, -1)}</em>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={key} className="rounded bg-slate-950/80 px-1 py-0.5 text-indigo-200">{part.slice(1, -1)}</code>;
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
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let paragraph: string[] = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`} className="whitespace-pre-wrap">
        {paragraph.flatMap((line, index) => [
          ...(index ? [<br key={`br-${blocks.length}-${index}`} />] : []),
          ...inlineMarkdown(line, `p-${blocks.length}-${index}`),
        ])}
      </p>,
    );
    paragraph = [];
  };

  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      const Tag = `h${level}` as ElementType;
      blocks.push(
        <Tag key={`h-${index}`} className="mb-2 mt-3 text-sm font-semibold text-white first:mt-0">
          {inlineMarkdown(heading[2], `h-${index}`)}
        </Tag>,
      );
      index += 1;
      continue;
    }

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
        <div key={`table-${index}`} className="my-3 overflow-x-auto rounded-lg border border-slate-700">
          <table className="min-w-full text-left text-[11px]">
            <thead className="bg-slate-800/80 text-slate-200">
              <tr>{header.map((cell, cellIndex) => <th key={cellIndex} className="px-3 py-2 font-semibold">{inlineMarkdown(cell, `th-${index}-${cellIndex}`)}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-slate-950/30 text-slate-300">
              {tableRows.map((row, rowIndex) => (
                <tr key={rowIndex} className="hover:bg-slate-800/40">
                  {header.map((_, cellIndex) => <td key={cellIndex} className="px-3 py-2 align-top">{inlineMarkdown(row[cellIndex] || "", `td-${index}-${rowIndex}-${cellIndex}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

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
        <ListTag key={`list-${index}`} className={`${orderedList ? "list-decimal" : "list-disc"} mb-2 ml-5 space-y-1`}>
          {items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item, `li-${index}-${itemIndex}`)}</li>)}
        </ListTag>,
      );
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
    } else {
      paragraph.push(line);
    }
    index += 1;
  }
  flushParagraph();

  return <div className="space-y-2 leading-relaxed">{blocks}</div>;
}
