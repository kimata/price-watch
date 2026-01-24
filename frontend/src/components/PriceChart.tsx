import { useMemo } from "react";
import { Line } from "react-chartjs-2";
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler,
} from "chart.js";
import type { ChartOptions } from "chart.js";
import dayjs from "dayjs";
import type { StoreEntry } from "../types";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

// ストア別の色定義
const STORE_COLORS = [
    { border: "rgb(59, 130, 246)", bg: "rgba(59, 130, 246, 0.1)" }, // Blue
    { border: "rgb(239, 68, 68)", bg: "rgba(239, 68, 68, 0.1)" }, // Red
    { border: "rgb(34, 197, 94)", bg: "rgba(34, 197, 94, 0.1)" }, // Green
    { border: "rgb(168, 85, 247)", bg: "rgba(168, 85, 247, 0.1)" }, // Purple
    { border: "rgb(249, 115, 22)", bg: "rgba(249, 115, 22, 0.1)" }, // Orange
    { border: "rgb(236, 72, 153)", bg: "rgba(236, 72, 153, 0.1)" }, // Pink
];

interface PriceChartProps {
    stores: StoreEntry[];
}

export default function PriceChart({ stores }: PriceChartProps) {
    const chartData = useMemo(() => {
        // 全ストアの履歴から日付を抽出してマージ
        const allDates = new Set<string>();
        stores.forEach((store) => {
            store.history.forEach((h) => {
                allDates.add(dayjs(h.time).format("YYYY-MM-DD"));
            });
        });

        // 日付をソート
        const sortedDates = Array.from(allDates).sort();
        const labels = sortedDates.map((d) => dayjs(d).format("MM/DD"));

        // ストアごとのデータセットを作成
        const datasets = stores.map((store, index) => {
            const colorIndex = index % STORE_COLORS.length;
            const color = STORE_COLORS[colorIndex];

            // 日付ごとの effective_price をマップ
            const priceMap = new Map<string, number>();
            store.history.forEach((h) => {
                const date = dayjs(h.time).format("YYYY-MM-DD");
                priceMap.set(date, h.effective_price);
            });

            // sortedDates に沿って値を配列化（欠損は null）
            const data = sortedDates.map((date) => priceMap.get(date) ?? null);

            return {
                label: store.store,
                data,
                borderColor: color.border,
                backgroundColor: stores.length === 1 ? color.bg : "transparent",
                fill: stores.length === 1,
                tension: 0.3,
                pointRadius: store.history.length > 30 ? 0 : 3,
                pointHoverRadius: 5,
                spanGaps: true,
            };
        });

        return { labels, datasets };
    }, [stores]);

    const options: ChartOptions<"line"> = useMemo(() => {
        // 全ストアの価格から min/max を計算
        const allPrices: number[] = [];
        stores.forEach((store) => {
            store.history.forEach((h) => {
                allPrices.push(h.effective_price);
            });
        });

        if (allPrices.length === 0) {
            return {};
        }

        const minPrice = Math.min(...allPrices);
        const maxPrice = Math.max(...allPrices);
        const padding = (maxPrice - minPrice) * 0.1 || maxPrice * 0.1;

        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: stores.length > 1,
                    position: "top" as const,
                    labels: {
                        boxWidth: 12,
                        font: { size: 10 },
                    },
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const value = context.parsed.y;
                            const storeName = context.dataset.label || "";
                            return value !== null ? `${storeName}: ${value.toLocaleString()}円` : "";
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: {
                        display: false,
                    },
                    ticks: {
                        maxTicksLimit: 6,
                        font: { size: 10 },
                    },
                },
                y: {
                    min: Math.max(0, minPrice - padding),
                    max: maxPrice + padding,
                    ticks: {
                        callback: (value) => `${Number(value).toLocaleString()}`,
                        font: { size: 10 },
                    },
                },
            },
        };
    }, [stores]);

    // 全ストアに履歴がない場合
    const hasHistory = stores.some((s) => s.history.length > 0);
    if (!hasHistory) {
        return (
            <div className="h-40 flex items-center justify-center text-gray-400 text-sm">
                データがありません
            </div>
        );
    }

    return (
        <div className="h-40">
            <Line data={chartData} options={options} />
        </div>
    );
}
