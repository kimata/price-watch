import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import App from "./App.tsx";
import { ToastProvider } from "./contexts/ToastContext.tsx";
import { SSEProvider } from "./contexts/SSEContext.tsx";
import { queryClient } from "./services/queryClient.ts";

createRoot(document.getElementById("root")!).render(
    <StrictMode>
        <QueryClientProvider client={queryClient}>
            <SSEProvider>
                <ToastProvider>
                    <App />
                </ToastProvider>
            </SSEProvider>
        </QueryClientProvider>
    </StrictMode>
);
