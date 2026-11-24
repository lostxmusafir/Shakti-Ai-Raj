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
    <html lang="en" className="dark">
      <body className="min-h-screen bg-synapse-bg text-synapse-text antialiased">
        {children}
      </body>
    </html>
  );
}
