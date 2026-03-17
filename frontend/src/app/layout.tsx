/**
 * Root layout — wraps every page with:
 *   - TanStack Query provider (QueryClientProvider)
 *   - React Hot Toast notifications
 *   - Persistent Sidebar + Header structure
 *
 * The QueryClient is created once per browser session in a client boundary
 * component to avoid hydration mismatches with Next.js App Router.
 */

import type { Metadata } from "next";
import "./globals.css";
import Providers from "./providers";
import Sidebar from "@/components/layout/Sidebar";

export const metadata: Metadata = {
  title: "GraphRL-Sec | SOC Dashboard",
  description:
    "Security Operations Centre powered by Graph Neural Networks and Deep Reinforcement Learning — real-time threat intelligence from network graphs.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>): React.ReactElement {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>
          <div className="flex h-screen overflow-hidden bg-[#0d1117]">
            {/* Left sidebar — fixed width */}
            <Sidebar />

            {/* Main content area — scrollable */}
            <main className="flex flex-1 flex-col overflow-hidden">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
