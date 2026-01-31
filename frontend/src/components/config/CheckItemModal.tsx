import { useState, useEffect, useCallback, useRef } from "react";
import { XMarkIcon, PlayIcon, CheckCircleIcon, ExclamationCircleIcon } from "@heroicons/react/24/outline";
import type { ItemDefinitionConfig, StoreDefinitionConfig } from "../../types/config";
import { API_BASE_URL } from "../../services/configService";

interface CheckItemModalProps {
    item: ItemDefinitionConfig;
    storeName: string;
    storeConfig: StoreDefinitionConfig;
    onClose: () => void;
}

interface LogEntry {
    id: number;
    type: "log" | "progress" | "error";
    message: string;
    timestamp: Date;
}

interface CheckResult {
    price: number | null;
    stock: string | null;
    thumb_url: string | null;
    crawl_status: string;
}

type JobStatus = "idle" | "running" | "completed" | "failed";

export default function CheckItemModal({
    item,
    storeName,
    storeConfig,
    onClose,
}: CheckItemModalProps) {
    const [status, setStatus] = useState<JobStatus>("idle");
    const [logs, setLogs] = useState<LogEntry[]>([]);
    const [result, setResult] = useState<CheckResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const logIdRef = useRef(0);
    const logsEndRef = useRef<HTMLDivElement>(null);
    const eventSourceRef = useRef<EventSource | null>(null);

    // ログを追加
    const addLog = useCallback((type: LogEntry["type"], message: string) => {
        setLogs((prev) => [
            ...prev,
            {
                id: logIdRef.current++,
                type,
                message,
                timestamp: new Date(),
            },
        ]);
    }, []);

    // ログの自動スクロール
    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    // クリーンアップ
    useEffect(() => {
        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
        };
    }, []);

    // チェック開始
    const handleStartCheck = useCallback(async () => {
        setStatus("running");
        setLogs([]);
        setResult(null);
        setError(null);

        addLog("log", "チェックを開始しています...");

        try {
            // ジョブを開始
            const response = await fetch(`${API_BASE_URL}/api/target/check-item`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    item: item,
                    store_name: storeName,
                    store_config: storeConfig,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || "ジョブの開始に失敗しました");
            }

            const { job_id } = await response.json();
            addLog("log", `ジョブ ID: ${job_id}`);

            // SSE でストリーミング受信
            const eventSource = new EventSource(
                `${API_BASE_URL}/api/target/check-item/${job_id}/stream`
            );
            eventSourceRef.current = eventSource;

            eventSource.addEventListener("log", ((event: MessageEvent) => {
                const data = JSON.parse(event.data);
                addLog("log", data.message);
            }) as EventListener);

            eventSource.addEventListener("progress", ((event: MessageEvent) => {
                const data = JSON.parse(event.data);
                addLog("progress", data.message);
            }) as EventListener);

            eventSource.addEventListener("result", ((event: MessageEvent) => {
                const data = JSON.parse(event.data);
                setResult(data);
                addLog("log", "結果を受信しました");
            }) as EventListener);

            eventSource.addEventListener("error", ((event: MessageEvent) => {
                try {
                    const data = JSON.parse(event.data);
                    setError(data.message);
                    addLog("error", data.message);
                } catch {
                    // SSE 接続エラー（パース失敗）の場合はスキップ
                }
            }) as EventListener);

            eventSource.addEventListener("done", ((event: MessageEvent) => {
                const data = JSON.parse(event.data);
                eventSource.close();
                eventSourceRef.current = null;

                if (data.status === "completed") {
                    setStatus("completed");
                    addLog("log", "チェック完了");
                } else {
                    setStatus("failed");
                    addLog("error", "チェック失敗");
                }
            }) as EventListener);

            eventSource.onerror = () => {
                eventSource.close();
                eventSourceRef.current = null;
                setStatus("failed");
                setError("接続エラーが発生しました");
                addLog("error", "接続エラーが発生しました");
            };
        } catch (err) {
            setStatus("failed");
            const message = err instanceof Error ? err.message : "不明なエラー";
            setError(message);
            addLog("error", message);
        }
    }, [item, storeName, storeConfig, addLog]);

    // 価格フォーマット
    const formatPrice = (price: number | null): string => {
        if (price === null) return "-";
        return price.toLocaleString();
    };

    // 在庫ステータスの表示
    const getStockLabel = (stock: string | null): string => {
        if (stock === null) return "不明";
        switch (stock) {
            case "in_stock":
                return "在庫あり";
            case "out_of_stock":
                return "在庫なし";
            default:
                return "不明";
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
                {/* ヘッダー */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-medium text-gray-900">
                            動作確認
                        </h2>
                        <p className="text-sm text-gray-500">
                            {item.name} @ {storeName}
                        </p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 text-gray-400 hover:text-gray-500 rounded-md"
                    >
                        <XMarkIcon className="w-5 h-5" />
                    </button>
                </div>

                {/* コンテンツ */}
                <div className="flex-1 overflow-hidden flex flex-col p-6">
                    {/* ステータス表示 */}
                    <div className="flex items-center gap-4 mb-4">
                        {status === "idle" && (
                            <button
                                onClick={handleStartCheck}
                                className="inline-flex items-center px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                            >
                                <PlayIcon className="w-4 h-4 mr-2" />
                                チェック開始
                            </button>
                        )}
                        {status === "running" && (
                            <div className="flex items-center text-blue-600">
                                <svg
                                    className="animate-spin w-5 h-5 mr-2"
                                    viewBox="0 0 24 24"
                                >
                                    <circle
                                        className="opacity-25"
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        stroke="currentColor"
                                        strokeWidth="4"
                                        fill="none"
                                    />
                                    <path
                                        className="opacity-75"
                                        fill="currentColor"
                                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                                    />
                                </svg>
                                <span>チェック中...</span>
                            </div>
                        )}
                        {status === "completed" && (
                            <div className="flex items-center text-green-600">
                                <CheckCircleIcon className="w-5 h-5 mr-2" />
                                <span>完了</span>
                            </div>
                        )}
                        {status === "failed" && (
                            <div className="flex items-center text-red-600">
                                <ExclamationCircleIcon className="w-5 h-5 mr-2" />
                                <span>失敗</span>
                            </div>
                        )}

                        {(status === "completed" || status === "failed") && (
                            <button
                                onClick={handleStartCheck}
                                className="inline-flex items-center px-3 py-1.5 text-sm text-blue-600 hover:text-blue-700"
                            >
                                <PlayIcon className="w-4 h-4 mr-1" />
                                再実行
                            </button>
                        )}
                    </div>

                    {/* 結果表示 */}
                    {result && (
                        <div className="mb-4 p-4 bg-gray-50 rounded-lg">
                            <h3 className="text-sm font-medium text-gray-900 mb-3">
                                結果
                            </h3>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-xs text-gray-500">価格</p>
                                    <p className="text-lg font-medium text-gray-900">
                                        {formatPrice(result.price)}
                                        {result.price !== null && (
                                            <span className="text-sm text-gray-500 ml-1">
                                                {storeConfig.price_unit}
                                            </span>
                                        )}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">在庫状況</p>
                                    <p className={`text-lg font-medium ${
                                        result.stock === "in_stock"
                                            ? "text-green-600"
                                            : result.stock === "out_of_stock"
                                            ? "text-red-600"
                                            : "text-gray-500"
                                    }`}>
                                        {getStockLabel(result.stock)}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-xs text-gray-500">クロール状況</p>
                                    <p className={`text-sm font-medium ${
                                        result.crawl_status === "success"
                                            ? "text-green-600"
                                            : "text-red-600"
                                    }`}>
                                        {result.crawl_status === "success" ? "成功" : "失敗"}
                                    </p>
                                </div>
                                {result.thumb_url && (
                                    <div>
                                        <p className="text-xs text-gray-500 mb-1">サムネイル</p>
                                        <img
                                            src={result.thumb_url}
                                            alt="サムネイル"
                                            className="w-16 h-16 object-contain border border-gray-200 rounded"
                                        />
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* エラー表示 */}
                    {error && !result && (
                        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                            <p className="text-sm text-red-700">{error}</p>
                        </div>
                    )}

                    {/* ログ表示 */}
                    <div className="flex-1 min-h-0">
                        <h3 className="text-sm font-medium text-gray-900 mb-2">
                            ログ
                        </h3>
                        <div className="h-48 overflow-y-auto bg-gray-900 rounded-lg p-3 font-mono text-xs">
                            {logs.length === 0 ? (
                                <p className="text-gray-500">
                                    チェック開始ボタンを押してください
                                </p>
                            ) : (
                                logs.map((log) => (
                                    <div
                                        key={log.id}
                                        className={`mb-1 ${
                                            log.type === "error"
                                                ? "text-red-400"
                                                : log.type === "progress"
                                                ? "text-blue-400"
                                                : "text-gray-300"
                                        }`}
                                    >
                                        <span className="text-gray-500">
                                            [{log.timestamp.toLocaleTimeString()}]
                                        </span>{" "}
                                        {log.message}
                                    </div>
                                ))
                            )}
                            <div ref={logsEndRef} />
                        </div>
                    </div>
                </div>

                {/* フッター */}
                <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
                    >
                        閉じる
                    </button>
                </div>
            </div>
        </div>
    );
}
