import { useState, useEffect, useCallback, useRef } from "react";
import { ArrowLeftIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import "dayjs/locale/ja";
import UptimeHeatmap from "./UptimeHeatmap";
import CrawlTimeBoxPlotChart from "./CrawlTimeBoxPlotChart";
import TotalCrawlTimeBoxPlotChart from "./TotalCrawlTimeBoxPlotChart";
import FailureTimeseriesChart from "./FailureTimeseriesChart";
import MetricsFooter from "./MetricsFooter";

dayjs.extend(relativeTime);
dayjs.locale("ja");

interface MetricsStatus {
    is_running: boolean;
    is_crawling: boolean;
    session_id: number | null;
    started_at: string | null;
    last_heartbeat_at: string | null;
    uptime_sec: number | null;
    total_items: number;
    success_items: number;
    failed_items: number;
}

interface MetricsPageProps {
    onBack: () => void;
}

// 期間オプション
const PERIOD_OPTIONS = [
    { value: 7, label: "7日" },
    { value: 30, label: "30日" },
    { value: 90, label: "90日" },
];

function formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
        return `${hours}時間${minutes}分`;
    }
    return `${minutes}分`;
}

function formatDateTime(isoString: string): { formatted: string; relative: string } {
    const d = dayjs(isoString);
    return {
        formatted: d.format("YYYY年M月D日 HH:mm:ss"),
        relative: d.fromNow(),
    };
}

function formatTime(date: Date): string {
    return date.toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

type ConnectionState = "connected" | "disconnected" | "connecting";

export default function MetricsPage({ onBack }: MetricsPageProps) {
    const [status, setStatus] = useState<MetricsStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [days, setDays] = useState(7);
    const [refreshKey, setRefreshKey] = useState(0);
    const [displayUptime, setDisplayUptime] = useState<number | null>(null);

    // SSE 接続状態
    const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
    const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
    const eventSourceRef = useRef<EventSource | null>(null);
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const fetchStatus = useCallback(async () => {
        try {
            const response = await fetch("/price/api/metrics/status");
            if (!response.ok) {
                throw new Error("Failed to fetch status");
            }
            const data = await response.json();
            setStatus(data);
            setDisplayUptime(data.uptime_sec);
            setError(null);
        } catch {
            setError("メトリクスの取得に失敗しました");
        } finally {
            setLoading(false);
        }
    }, []);

    const handleRefresh = useCallback(() => {
        setRefreshKey((prev) => prev + 1);
        fetchStatus();
        setLastUpdate(new Date());
    }, [fetchStatus]);

    // SSE 接続
    const connectSSE = useCallback(() => {
        if (eventSourceRef.current) {
            eventSourceRef.current.close();
        }

        setConnectionState("connecting");

        const eventSource = new EventSource("/price/api/event");

        eventSource.onopen = () => {
            setConnectionState("connected");
            setLastUpdate(new Date());
        };

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "control") {
                    handleRefresh();
                }
            } catch {
                // パースエラーは無視
            }
        };

        eventSource.onerror = () => {
            eventSource.close();
            setConnectionState("disconnected");

            // 5秒後に再接続
            reconnectTimerRef.current = setTimeout(() => {
                connectSSE();
            }, 5000);
        };

        eventSourceRef.current = eventSource;
    }, [handleRefresh]);

    // SSE 接続の開始・クリーンアップ
    useEffect(() => {
        connectSSE();

        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
            }
        };
    }, [connectSSE]);

    // 初回読み込みと定期更新（SSE が切れた場合のフォールバック）
    useEffect(() => {
        fetchStatus();
        const interval = setInterval(fetchStatus, 30000);
        return () => clearInterval(interval);
    }, [fetchStatus]);

    // 稼働時間のリアルタイム更新
    useEffect(() => {
        if (!status?.is_running || displayUptime === null) return;

        const interval = setInterval(() => {
            setDisplayUptime((prev) => (prev !== null ? prev + 1 : null));
        }, 1000);

        return () => clearInterval(interval);
    }, [status?.is_running, displayUptime]);

    // 稼働状態の表示テキストとスタイル
    const getRunningStateDisplay = () => {
        if (!status?.is_running) {
            return { text: "停止中", dotClass: "bg-gray-400" };
        }
        if (status.is_crawling) {
            return { text: "巡回中", dotClass: "bg-green-500 animate-pulse" };
        }
        return { text: "スリープ中", dotClass: "bg-yellow-400" };
    };

    const runningState = status ? getRunningStateDisplay() : null;

    // 接続状態インジケーター
    const getConnectionIndicator = () => {
        switch (connectionState) {
            case "connected":
                return {
                    dotClass: "bg-green-500",
                    label: "リアルタイム更新",
                };
            case "disconnected":
                return {
                    dotClass: "bg-orange-400",
                    label: "再接続中...",
                };
            case "connecting":
                return {
                    dotClass: "bg-gray-400 animate-pulse",
                    label: "接続中...",
                };
        }
    };

    const connectionIndicator = getConnectionIndicator();

    return (
        <div className="min-h-screen bg-gray-100">
            {/* ヘッダー */}
            <header className="bg-white shadow">
                <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <button
                            onClick={onBack}
                            className="cursor-pointer p-2 text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-full transition-colors"
                            title="戻る"
                        >
                            <ArrowLeftIcon className="h-5 w-5" />
                        </button>
                        <h1 className="text-xl font-bold text-gray-800">巡回メトリクス</h1>
                    </div>
                    {/* リアルタイム更新インジケーター */}
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                        <span className={`w-2 h-2 rounded-full ${connectionIndicator.dotClass}`}></span>
                        <span>{connectionIndicator.label}</span>
                        {lastUpdate && connectionState === "connected" && (
                            <span className="text-gray-400">{formatTime(lastUpdate)}</span>
                        )}
                    </div>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
                {loading ? (
                    <div className="bg-white rounded-lg shadow p-6">
                        <div className="animate-pulse space-y-4">
                            <div className="h-4 bg-gray-200 rounded w-1/4"></div>
                            <div className="h-8 bg-gray-200 rounded w-1/2"></div>
                        </div>
                    </div>
                ) : error ? (
                    <div className="bg-white rounded-lg shadow p-6">
                        <p className="text-red-600 text-center">{error}</p>
                        <button
                            onClick={handleRefresh}
                            className="mt-4 mx-auto block px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                        >
                            再読み込み
                        </button>
                    </div>
                ) : (
                    <>
                        {/* 現在の状態 */}
                        <div className="bg-white rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-800 mb-4">現在の状態</h2>
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                                {/* 稼働状態 */}
                                <div className="bg-gray-50 rounded-lg p-4">
                                    <p className="text-sm text-gray-500 mb-1">稼働状態</p>
                                    <div className="flex items-center gap-2">
                                        <span
                                            className={`w-3 h-3 rounded-full ${runningState?.dotClass ?? "bg-gray-400"}`}
                                        ></span>
                                        <span className="text-lg font-semibold">
                                            {runningState?.text ?? "不明"}
                                        </span>
                                    </div>
                                </div>

                                {/* 稼働時間 */}
                                <div className="bg-gray-50 rounded-lg p-4">
                                    <p className="text-sm text-gray-500 mb-1">稼働時間</p>
                                    <p className="text-lg font-semibold">
                                        {displayUptime !== null ? formatDuration(displayUptime) : "-"}
                                    </p>
                                </div>

                                {/* 巡回アイテム数 */}
                                <div className="bg-gray-50 rounded-lg p-4">
                                    <p className="text-sm text-gray-500 mb-1">巡回アイテム数</p>
                                    <p className="text-lg font-semibold">
                                        {status?.total_items ?? 0}
                                        <span className="text-sm text-gray-500 ml-1">
                                            (成功: {status?.success_items ?? 0}, 失敗:{" "}
                                            {status?.failed_items ?? 0})
                                        </span>
                                    </p>
                                </div>

                                {/* 最終ハートビート */}
                                <div className="bg-gray-50 rounded-lg p-4">
                                    <p className="text-sm text-gray-500 mb-1">最終ハートビート</p>
                                    {status?.last_heartbeat_at ? (
                                        <>
                                            <p className="text-lg font-semibold">
                                                {formatDateTime(status.last_heartbeat_at).formatted}
                                            </p>
                                            <p className="text-sm text-gray-500">
                                                {formatDateTime(status.last_heartbeat_at).relative}
                                            </p>
                                        </>
                                    ) : (
                                        <p className="text-lg font-semibold">-</p>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* ヒートマップ */}
                        <div className="bg-white rounded-lg shadow p-6">
                            <div className="flex items-center justify-between mb-4">
                                <h2 className="text-lg font-semibold text-gray-800">稼働率ヒートマップ</h2>
                                <div className="flex items-center gap-2">
                                    {PERIOD_OPTIONS.map((option) => (
                                        <button
                                            key={option.value}
                                            onClick={() => setDays(option.value)}
                                            className={`px-3 py-1 text-sm rounded-md transition-colors ${
                                                days === option.value
                                                    ? "bg-blue-600 text-white"
                                                    : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                                            }`}
                                        >
                                            {option.label}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <UptimeHeatmap days={days} refreshKey={refreshKey} />
                            <div className="mt-4 flex items-center justify-center gap-4 text-sm text-gray-600">
                                <span>稼働率:</span>
                                <div className="flex items-center gap-1">
                                    <span
                                        className="w-4 h-4 rounded"
                                        style={{ backgroundColor: "#e0e0e0" }}
                                    ></span>
                                    <span>0-20%</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span
                                        className="w-4 h-4 rounded"
                                        style={{ backgroundColor: "#fff59d" }}
                                    ></span>
                                    <span>20-40%</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span
                                        className="w-4 h-4 rounded"
                                        style={{ backgroundColor: "#ffee58" }}
                                    ></span>
                                    <span>40-60%</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span
                                        className="w-4 h-4 rounded"
                                        style={{ backgroundColor: "#a5d610" }}
                                    ></span>
                                    <span>60-80%</span>
                                </div>
                                <div className="flex items-center gap-1">
                                    <span
                                        className="w-4 h-4 rounded"
                                        style={{ backgroundColor: "#4caf50" }}
                                    ></span>
                                    <span>80-100%</span>
                                </div>
                            </div>
                        </div>

                        {/* 巡回統計 */}
                        <div className="bg-white rounded-lg shadow p-6">
                            <h2 className="text-lg font-semibold text-gray-800 mb-4">巡回統計</h2>
                            <div className="space-y-4">
                                {/* 全体巡回時間 時系列箱ひげ図 */}
                                <div className="bg-gray-50 rounded-lg shadow-sm border border-gray-200 p-4">
                                    <h3 className="text-sm font-medium text-gray-600 mb-2">
                                        全体巡回時間
                                    </h3>
                                    <TotalCrawlTimeBoxPlotChart days={days} refreshKey={refreshKey} />
                                </div>

                                {/* ストア別巡回時間 時系列箱ひげ図 */}
                                <CrawlTimeBoxPlotChart days={days} refreshKey={refreshKey} />

                                {/* 失敗数時系列 */}
                                <div className="bg-gray-50 rounded-lg shadow-sm border border-gray-200 p-4">
                                    <h3 className="text-sm font-medium text-gray-600 mb-2">
                                        巡回失敗数（1時間あたり）
                                    </h3>
                                    <FailureTimeseriesChart days={days} refreshKey={refreshKey} />
                                </div>
                            </div>
                        </div>
                    </>
                )}
            </main>

            <MetricsFooter />
        </div>
    );
}
