import { useState, useEffect, useRef } from "react";

interface BoxPlotStats {
    min: number;
    q1: number;
    median: number;
    q3: number;
    max: number;
    count: number;
    outliers: number[];
}

interface CrawlTimeBoxPlotResponse {
    stores: Record<string, BoxPlotStats>;
    total: BoxPlotStats | null;
}

interface TotalCrawlTimeBoxPlotChartProps {
    days: number;
    refreshKey: number;
}

function formatTime(sec: number): string {
    if (sec < 60) {
        return `${sec.toFixed(1)}秒`;
    }
    const min = Math.floor(sec / 60);
    const remainSec = sec % 60;
    return `${min}分${remainSec.toFixed(0)}秒`;
}

export default function TotalCrawlTimeBoxPlotChart({
    days,
    refreshKey,
}: TotalCrawlTimeBoxPlotChartProps) {
    const [chartData, setChartData] = useState<CrawlTimeBoxPlotResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chartRef = useRef<any>(null);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const response = await fetch(`/price/api/metrics/crawl-time/boxplot?days=${days}`);
                if (!response.ok) throw new Error("Failed to fetch");
                const data = await response.json();
                setChartData(data);
            } catch (error) {
                console.error("Failed to fetch total crawl time boxplot data:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [days, refreshKey]);

    useEffect(() => {
        if (!chartData?.total || !canvasRef.current) return;

        const loadBoxplot = async () => {
            try {
                const { Chart, CategoryScale, LinearScale, LineController, LineElement, PointElement } =
                    await import("chart.js");
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

                const stats = chartData.total;
                if (!stats) return;

                const boxplotData = [
                    {
                        min: stats.min,
                        q1: stats.q1,
                        median: stats.median,
                        q3: stats.q3,
                        max: stats.max,
                        outliers: stats.outliers,
                    },
                ];

                chartRef.current = new Chart(ctx, {
                    type: "boxplot",
                    data: {
                        labels: ["全体"],
                        datasets: [
                            {
                                label: "全体巡回時間分布",
                                data: boxplotData,
                                backgroundColor: "rgba(59, 130, 246, 0.7)",
                                borderColor: "rgb(59, 130, 246)",
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
                        indexAxis: "y",
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
                                    title: () => "全体巡回時間",
                                    label: () => {
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
                            x: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: "巡回時間（秒）",
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
        };

        loadBoxplot();

        return () => {
            if (chartRef.current) {
                chartRef.current.destroy();
            }
        };
    }, [chartData]);

    if (loading) {
        return (
            <div className="h-[120px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (!chartData?.total) {
        return (
            <div className="h-[120px] flex items-center justify-center text-gray-500">
                データがありません
            </div>
        );
    }

    return (
        <div className="h-[120px]">
            <canvas ref={canvasRef} />
        </div>
    );
}
