import { useState, useEffect, useRef, useCallback } from "react";
import { formatDateToJapanese } from "../utils/dateFormat";

interface TimeseriesBoxPlotResponse {
    periods: string[];
    total: Record<string, number[]>;
    stores: Record<string, Record<string, number[]>>;
}

interface BoxplotStats {
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
    count: number;
}

interface CrawlTimeBoxPlotChartProps {
    days: number;
    refreshKey: number;
}

const STORE_COLORS: Record<string, { bg: string; border: string }> = {
    Amazon: { bg: "rgba(255, 153, 0, 0.6)", border: "rgb(255, 153, 0)" },
    アマゾン: { bg: "rgba(255, 153, 0, 0.6)", border: "rgb(255, 153, 0)" },
    ヨドバシ: { bg: "rgba(204, 0, 0, 0.6)", border: "rgb(204, 0, 0)" },
    メルカリ: { bg: "rgba(255, 80, 80, 0.6)", border: "rgb(255, 80, 80)" },
    ラクマ: { bg: "rgba(110, 64, 170, 0.6)", border: "rgb(110, 64, 170)" },
    PayPayフリマ: { bg: "rgba(255, 0, 85, 0.6)", border: "rgb(255, 0, 85)" },
    PayPay: { bg: "rgba(255, 0, 85, 0.6)", border: "rgb(255, 0, 85)" },
    Yahoo: { bg: "rgba(255, 0, 51, 0.6)", border: "rgb(255, 0, 51)" },
    ヤフー: { bg: "rgba(255, 0, 51, 0.6)", border: "rgb(255, 0, 51)" },
    "UI Store (US)": { bg: "rgba(0, 123, 255, 0.6)", border: "rgb(0, 123, 255)" },
};

const DEFAULT_COLOR = { bg: "rgba(160, 160, 160, 0.6)", border: "rgb(130, 130, 130)" };

function calculateBoxplotStats(values: number[]): BoxplotStats | null {
    if (!values || values.length === 0) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const n = sorted.length;
    const min = sorted[0];
    const max = sorted[n - 1];
    const median = n % 2 === 0 ? (sorted[n / 2 - 1] + sorted[n / 2]) / 2 : sorted[Math.floor(n / 2)];
    const q1Index = (n - 1) * 0.25;
    const q3Index = (n - 1) * 0.75;
    const q1 =
        sorted[Math.floor(q1Index)] +
        (q1Index % 1) * (sorted[Math.ceil(q1Index)] - sorted[Math.floor(q1Index)]);
    const q3 =
        sorted[Math.floor(q3Index)] +
        (q3Index % 1) * (sorted[Math.ceil(q3Index)] - sorted[Math.floor(q3Index)]);
    return { min, q1, median, q3, max, count: n };
}

function formatTime(sec: number): string {
    if (sec < 60) {
        return `${sec.toFixed(1)}秒`;
    }
    const min = Math.floor(sec / 60);
    const remainSec = sec % 60;
    return `${min}分${remainSec.toFixed(0)}秒`;
}

function StoreBoxPlotChart({
    storeName,
    periods,
    storeData,
}: {
    storeName: string;
    periods: string[];
    storeData: Record<string, number[]>;
}) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chartRef = useRef<any>(null);

    const renderChart = useCallback(async () => {
        if (!canvasRef.current) return;

        try {
            const {
                Chart,
                CategoryScale,
                LinearScale,
                LineController,
                LineElement,
                PointElement,
            } = await import("chart.js");
            const { BoxPlotController, BoxAndWiskers } = await import(
                "@sgratzl/chartjs-chart-boxplot"
            );

            Chart.register(
                CategoryScale,
                LinearScale,
                LineController,
                LineElement,
                PointElement,
                BoxPlotController,
                BoxAndWiskers,
            );

            if (chartRef.current) {
                chartRef.current.destroy();
            }

            const ctx = canvasRef.current?.getContext("2d");
            if (!ctx) return;

            const periodsWithData = periods.filter(
                (p) => storeData[p] && storeData[p].length > 0,
            );

            if (periodsWithData.length === 0) return;

            const boxplotData = periodsWithData.map((p) => storeData[p] || []);
            const originalStats = periodsWithData.map((p) =>
                calculateBoxplotStats(storeData[p] || []),
            );
            const formattedLabels = periodsWithData.map(formatDateToJapanese);

            const colors = STORE_COLORS[storeName] || DEFAULT_COLOR;

            chartRef.current = new Chart(ctx, {
                type: "boxplot",
                data: {
                    labels: formattedLabels,
                    datasets: [
                        {
                            label: `巡回時間（${storeName}）`,
                            data: boxplotData,
                            backgroundColor: colors.bg,
                            borderColor: colors.border,
                            borderWidth: 2,
                            outlierColor: "rgb(239, 68, 68)",
                            medianColor: "rgb(255, 193, 7)",
                            // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        } as any,
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            backgroundColor: "rgba(0, 0, 0, 0.8)",
                            titleColor: "white",
                            bodyColor: "white",
                            borderColor: "rgba(255, 255, 255, 0.3)",
                            borderWidth: 1,
                            padding: 10,
                            displayColors: true,
                            callbacks: {
                                title: (context: { label: string }[]) => context[0].label,
                                label: (context: { dataIndex: number }) => {
                                    const stats = originalStats[context.dataIndex];
                                    if (!stats) return "データなし";
                                    return [
                                        `最小値: ${formatTime(stats.min)}`,
                                        `第1四分位: ${formatTime(stats.q1)}`,
                                        `中央値: ${formatTime(stats.median)}`,
                                        `第3四分位: ${formatTime(stats.q3)}`,
                                        `最大値: ${formatTime(stats.max)}`,
                                        `データ数: ${stats.count}`,
                                    ];
                                },
                            },
                        },
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: "巡回時間",
                                font: { size: 12, weight: "bold" },
                            },
                            ticks: {
                                callback: (value: number | string) => {
                                    const v = Number(value);
                                    if (v < 60) return `${v}秒`;
                                    const min = Math.floor(v / 60);
                                    const sec = v % 60;
                                    return sec > 0 ? `${min}分${sec}秒` : `${min}分`;
                                },
                            },
                        },
                    },
                },
            });
        } catch {
            console.warn("Boxplot chart not available");
        }
    }, [storeName, periods, storeData]);

    useEffect(() => {
        renderChart();
        return () => {
            if (chartRef.current) {
                chartRef.current.destroy();
            }
        };
    }, [renderChart]);

    return (
        <div className="h-[300px]">
            <canvas ref={canvasRef} />
        </div>
    );
}

export default function CrawlTimeBoxPlotChart({ days, refreshKey }: CrawlTimeBoxPlotChartProps) {
    const [chartData, setChartData] = useState<TimeseriesBoxPlotResponse | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const response = await fetch(
                    `/price/api/metrics/crawl-time/timeseries-boxplot?days=${days}`,
                );
                if (!response.ok) throw new Error("Failed to fetch");
                const data = await response.json();
                setChartData(data);
            } catch (error) {
                console.error("Failed to fetch crawl time timeseries data:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [days, refreshKey]);

    if (loading) {
        return (
            <div className="h-[300px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (!chartData?.stores || !Object.keys(chartData.stores).length) {
        return (
            <div className="h-[300px] flex items-center justify-center text-gray-500">
                データがありません
            </div>
        );
    }

    const storeNames = Object.keys(chartData.stores);

    return (
        <div className="space-y-6">
            {storeNames.map((storeName) => {
                // ストアにデータがあるか確認
                const storeData = chartData.stores[storeName];
                const hasData = chartData.periods.some(
                    (p) => storeData[p] && storeData[p].length > 0,
                );
                if (!hasData) return null;

                return (
                    <div key={storeName}>
                        <h3 className="text-sm font-medium text-gray-600 mb-2">
                            巡回時間（{storeName}）
                        </h3>
                        <StoreBoxPlotChart
                            storeName={storeName}
                            periods={chartData.periods}
                            storeData={storeData}
                        />
                    </div>
                );
            })}
        </div>
    );
}
