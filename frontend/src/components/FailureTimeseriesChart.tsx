import { useState, useEffect, useRef } from "react";

interface FailureTimeseriesResponse {
    labels: string[];
    data: number[];
}

interface FailureTimeseriesChartProps {
    days: number;
    refreshKey: number;
}

export default function FailureTimeseriesChart({ days, refreshKey }: FailureTimeseriesChartProps) {
    const [chartData, setChartData] = useState<FailureTimeseriesResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const chartRef = useRef<any>(null);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const response = await fetch(`/price/api/metrics/failures/timeseries?days=${days}`);
                if (!response.ok) throw new Error("Failed to fetch");
                const data = await response.json();
                setChartData(data);
            } catch (error) {
                console.error("Failed to fetch failure timeseries data:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [days, refreshKey]);

    useEffect(() => {
        if (!chartData || !canvasRef.current) return;

        const loadChart = async () => {
            try {
                const {
                    Chart,
                    CategoryScale,
                    LinearScale,
                    BarController,
                    BarElement,
                    Tooltip,
                    Legend,
                    TimeScale,
                } = await import("chart.js");

                Chart.register(
                    CategoryScale,
                    LinearScale,
                    BarController,
                    BarElement,
                    Tooltip,
                    Legend,
                    TimeScale,
                );

                if (chartRef.current) {
                    chartRef.current.destroy();
                }

                const ctx = canvasRef.current?.getContext("2d");
                if (!ctx) return;

                // ラベルを短縮表示（日付部分のみ表示、時間は6時間ごと）
                const displayLabels = chartData.labels.map((label) => {
                    const parts = label.split(" ");
                    const datePart = parts[0]; // YYYY-MM-DD
                    const timePart = parts[1]; // HH:00
                    const hour = parseInt(timePart.split(":")[0]);
                    if (hour === 0) {
                        // 日付の変わり目
                        const d = datePart.split("-");
                        return `${parseInt(d[1])}/${parseInt(d[2])}`;
                    }
                    if (hour % 6 === 0) {
                        return `${hour}:00`;
                    }
                    return "";
                });

                chartRef.current = new Chart(ctx, {
                    type: "bar",
                    data: {
                        labels: displayLabels,
                        datasets: [
                            {
                                label: "失敗数",
                                data: chartData.data,
                                backgroundColor: "rgba(239, 68, 68, 0.7)",
                                borderColor: "rgb(239, 68, 68)",
                                borderWidth: 1,
                            },
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
                                callbacks: {
                                    title: (context) => {
                                        const idx = context[0].dataIndex;
                                        return chartData.labels[idx];
                                    },
                                    label: (context) => `失敗数: ${context.parsed.y}`,
                                },
                            },
                        },
                        scales: {
                            x: {
                                ticks: {
                                    maxRotation: 0,
                                    autoSkip: false,
                                    font: { size: 10 },
                                },
                                grid: {
                                    display: false,
                                },
                            },
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: "失敗数",
                                    font: { size: 12, weight: "bold" },
                                },
                                ticks: {
                                    stepSize: 1,
                                },
                            },
                        },
                    },
                });
            } catch {
                console.warn("Failure timeseries chart not available");
            }
        };

        loadChart();

        return () => {
            if (chartRef.current) {
                chartRef.current.destroy();
            }
        };
    }, [chartData]);

    if (loading) {
        return (
            <div className="h-[250px] flex items-center justify-center">
                <div className="animate-spin h-8 w-8 border-4 border-blue-500 border-t-transparent rounded-full"></div>
            </div>
        );
    }

    if (!chartData || !chartData.data.some((v) => v > 0)) {
        return (
            <div className="h-[250px] flex items-center justify-center text-gray-500">
                失敗データがありません
            </div>
        );
    }

    return (
        <div className="h-[250px]">
            <canvas ref={canvasRef} />
        </div>
    );
}
