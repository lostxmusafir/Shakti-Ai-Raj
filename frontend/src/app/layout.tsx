import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Universal AI Analyst",
  description: "Internal, policy-aware enterprise data analyst",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[var(--background)] text-slate-100 antialiased">
        {children}
      </body>
    </html>
  );
}
