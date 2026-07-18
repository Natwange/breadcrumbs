import type { Metadata } from "next";

import { AuthProvider } from "@/components/AuthProvider";
import SentryInit from "@/components/SentryInit";
import "./globals.css";

export const metadata: Metadata = {
  title: "breadcrumbs — AI Incident Investigation Workspace",
  description:
    "Follow a trail of evidence across engineering systems to find the root cause of production outages.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <SentryInit />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
