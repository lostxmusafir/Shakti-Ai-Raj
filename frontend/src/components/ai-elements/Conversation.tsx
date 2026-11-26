"use client";

import { memo, type ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * Conversation scroll container with a centered, readable column.
 * Keeps the existing page scroll model; no extra providers required.
 */
export function Conversation({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex-1 overflow-y-auto", className)}>
      <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-6">{children}</div>
    </div>
  );
}

export default Conversation;
