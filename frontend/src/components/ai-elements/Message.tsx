"use client";

import { memo, type ReactNode } from "react";
import { Bot, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/cn";

type Role = "user" | "assistant" | "system";

/**
 * Message shell. Assistant answers render as plain, readable prose (no card),
 * user turns render as a restrained bubble on the right.
 */
export function Message({
  role,
  children,
  className,
  name,
}: {
  role: Role;
  children: ReactNode;
  className?: string;
  name?: string;
}) {
  const isUser = role === "user";

  if (isUser) {
    return (
      <div className={cn("flex justify-end gap-3", className)}>
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-slate-800/80 px-4 py-2.5 text-[13.5px] leading-6 text-slate-100 ring-1 ring-inset ring-white/5">
          {children}
        </div>
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-800 text-slate-400 ring-1 ring-inset ring-white/5">
          <UserIcon className="h-3.5 w-3.5" />
        </div>
      </div>
    );
  }

  return (
    <div className={cn("flex gap-3.5", className)}>
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/[0.08] text-[var(--accent)] ring-1 ring-inset ring-white/10">
        <Bot className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        {name ? <div className="mb-1 text-[11px] font-medium text-slate-400">{name}</div> : null}
        {children}
      </div>
    </div>
  );
}

export const MessageMeta = memo(function MessageMeta({ children }: { children: ReactNode }) {
  return <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">{children}</div>;
});

export default Message;
