"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getStoredToken } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const token = getStoredToken();
    if (token) {
      router.push("/chat");
    } else {
      router.push("/login");
    }
  }, [router]);

  return (
    <div className="flex h-screen items-center justify-center bg-slate-950">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
    </div>
  );
}
