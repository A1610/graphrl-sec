"use client";

/**
 * Providers — client boundary that initialises all React context providers.
 *
 * Separated from layout.tsx so that the root layout can remain a server
 * component (Metadata, fonts, etc.) while state providers live here.
 */

import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";

interface ProvidersProps {
  children: React.ReactNode;
}

export default function Providers({ children }: ProvidersProps): React.ReactElement {
  // useState ensures a single QueryClient instance per browser session
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 2,
            retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#161b22",
            color: "#e6edf3",
            border: "1px solid #30363d",
            fontSize: "13px",
          },
          success: { iconTheme: { primary: "#3fb950", secondary: "#161b22" } },
          error: { iconTheme: { primary: "#f85149", secondary: "#161b22" } },
        }}
      />
    </QueryClientProvider>
  );
}
