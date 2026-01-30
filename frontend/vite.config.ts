/// <reference types="vite/client" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig({
    plugins: [react(), tailwindcss()],
    base: "/price/",
    define: {
        "import.meta.env.VITE_BUILD_DATE": JSON.stringify(new Date().toISOString()),
    },
    build: {
        rollupOptions: {
            output: {
                manualChunks: {
                    // Chart.js と関連ライブラリを分離
                    charts: [
                        "chart.js",
                        "react-chartjs-2",
                        "@sgratzl/chartjs-chart-boxplot",
                        "chartjs-plugin-annotation",
                    ],
                    // React コアを分離
                    react: ["react", "react-dom"],
                },
            },
        },
    },
    server: {
        proxy: {
            "/price/api": {
                target: "http://localhost:5000",
                changeOrigin: true,
            },
        },
    },
});
