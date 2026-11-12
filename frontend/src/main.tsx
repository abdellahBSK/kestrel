import "./index.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Tooltip } from "radix-ui";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 2, staleTime: 1000, refetchOnWindowFocus: true } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delayDuration={250} skipDelayDuration={100}>
        <App />
      </Tooltip.Provider>
    </QueryClientProvider>
  </StrictMode>,
);
