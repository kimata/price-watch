import { useMemo, useState, useCallback } from "react";
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
import type { ChartOptions, LegendItem, ChartEvent } from "chart.js";
import annotationPlugin from "chartjs-plugin-annotation";
import type { AnnotationOptions } from "chartjs-plugin-annotation";
import dayjs from "dayjs";
import type { StoreEntry, StoreDefinition } from "../types";
import { formatPriceForChart, formatPriceForYAxis } from "../utils/formatPrice";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler, annotationPlugin);

// デフォルトの色（target.yaml で color が指定されていない場合）
const DEFAULT_COLORS = [
    { border: "rgb(59, 130, 246)", bg: "rgba(59, 130, 246, 0.1)" }, // Blue
    { border: "rgb(239, 68, 68)", bg: "rgba(239, 68, 68, 0.1)" }, // Red
    { border: "rgb(34, 197, 94)", bg: "rgba(34, 197, 94, 0.1)" }, // Green
    { border: "rgb(168, 85, 247)", bg: "rgba(168, 85, 247, 0.1)" }, // Purple
    { border: "rgb(249, 115, 22)", bg: "rgba(249, 115, 22, 0.1)" }, // Orange
    { border: "rgb(236, 72, 153)", bg: "rgba(236, 72, 153, 0.1)" }, // Pink
];

/**
 * Hex カラーコードを RGB に変換
 */
function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result
        ? {
              r: parseInt(result[1], 16),
              g: parseInt(result[2], 16),
              b: parseInt(result[3], 16),
          }
        : null;
}

/**
 * ストア名から色を取得
 */
function getStoreColor(
    storeName: string,
    storeDefinitions: StoreDefinition[],
    fallbackIndex: number
): { border: string; bg: string } {
    const storeDef = storeDefinitions.find((s) => s.name === storeName);
    if (storeDef?.color) {
        const rgb = hexToRgb(storeDef.color);
        if (rgb) {
            return {
                border: `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`,
                bg: `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.1)`,
            };
        }
    }
    // フォールバック: デフォルト色を使用
    return DEFAULT_COLORS[fallbackIndex % DEFAULT_COLORS.length];
}

/**
 * 全ストアで在庫なしの期間を検出
 * 連続した在庫なし期間を配列で返す
 * 条件: データがあるストアのうち、全て在庫なしの場合
 * 注意: 同じ時間帯に複数のデータがある場合、1つでも在庫ありなら在庫ありとみなす
 */
function findOutOfStockPeriods(
    stores: StoreEntry[],
    sortedTimes: string[]
): { start: number; end: number }[] {
    if (stores.length === 0 || sortedTimes.length === 0) {
        return [];
    }

    const periods: { start: number; end: number }[] = [];
    let periodStart: number | null = null;

    for (let i = 0; i < sortedTimes.length; i++) {
        const time = sortedTimes[i];

        // この時間でデータがあるストアのうち、全て在庫なしかどうかをチェック
        let hasDataForTime = false;
        let anyInStock = false;

        for (const store of stores) {
            // 同じ時間帯の全てのエントリをチェック（1つでも在庫ありなら在庫ありとみなす）
            const historyItems = store.history.filter(
                (h) => dayjs(h.time).format("YYYY-MM-DD HH:00") === time
            );
            if (historyItems.length > 0) {
                hasDataForTime = true;
                // この時間帯で1つでも在庫ありがあれば在庫ありとみなす
                if (historyItems.some((h) => h.stock !== 0)) {
                    anyInStock = true;
                    break;
                }
            }
        }

        // データがあり、かつ全て在庫なしの場合のみ灰色にする
        if (hasDataForTime && !anyInStock) {
            if (periodStart === null) {
                periodStart = i;
            }
        } else {
            if (periodStart !== null) {
                periods.push({ start: periodStart, end: i - 1 });
                periodStart = null;
            }
        }
    }

    // 最後まで在庫なしが続いている場合
    if (periodStart !== null) {
        periods.push({ start: periodStart, end: sortedTimes.length - 1 });
    }

    return periods;
}

interface PriceChartProps {
    stores: StoreEntry[];
    storeDefinitions: StoreDefinition[];
    className?: string;
    period?: string; // "30", "90", "180", "365", "all"
    largeLabels?: boolean; // 個別ページ用の大きめラベル
}

export default function PriceChart({ stores, storeDefinitions, className = "h-40", period: _period = "30", largeLabels = false }: PriceChartProps) {
    // 選択された系列（null の場合は全て表示）
    const [selectedLabel, setSelectedLabel] = useState<string | null>(null);

    // 最初のストアの通貨単位を取得（同一アイテムのストアは同じ通貨単位を持つと仮定）
    const priceUnit = stores[0]?.price_unit ?? "円";

    // 凡例クリックハンドラ
    const handleLegendClick = useCallback(
        (_event: ChartEvent, legendItem: LegendItem) => {
            const clickedLabel = legendItem.text;
            if (selectedLabel === clickedLabel) {
                // 同じラベルをクリック → 全表示に戻す
                setSelectedLabel(null);
            } else {
                // 別のラベルをクリック → その系列のみ表示
                setSelectedLabel(clickedLabel);
            }
        },
        [selectedLabel]
    );

    // 全て表示ボタンのハンドラ
    const handleShowAll = useCallback(() => {
        setSelectedLabel(null);
    }, []);

    const { chartData, sortedTimes } = useMemo(() => {
        // 全ストアの履歴から日時を抽出してマージ
        const allTimes = new Set<string>();
        stores.forEach((store) => {
            store.history.forEach((h) => {
                // 時間単位でグルーピング（分は切り捨て）
                allTimes.add(dayjs(h.time).format("YYYY-MM-DD HH:00"));
            });
        });

        // 現在時刻も追加（グラフの終点を現在時刻にする）
        const now = dayjs();
        allTimes.add(now.format("YYYY-MM-DD HH:00"));

        // 日時をソート
        const sortedTimes = Array.from(allTimes).sort();

        // ラベルの表示形式をデータの期間に応じて調整
        const formatLabel = (timeStr: string, _index: number, allTimes: string[]): string => {
            const time = dayjs(timeStr);
            const firstTime = dayjs(allTimes[0]);
            const lastTime = dayjs(allTimes[allTimes.length - 1]);
            const spanDays = lastTime.diff(firstTime, "day");

            if (spanDays <= 3) {
                // 3日以内：日付と時刻
                return time.format("M月D日 H:mm");
            } else {
                // 3日超：日付のみ（ラベルが長くなりすぎるため時刻は省略）
                return time.format("M月D日");
            }
        };

        const labels = sortedTimes.map((t, i) => formatLabel(t, i, sortedTimes));

        // ストアごとのデータセットを作成
        const datasets = stores.map((store, index) => {
            const color = getStoreColor(store.store, storeDefinitions, index);

            // 時間ごとの effective_price をマップ（null も保持）
            const priceMap = new Map<string, number | null>();
            store.history.forEach((h) => {
                const time = dayjs(h.time).format("YYYY-MM-DD HH:00");
                priceMap.set(time, h.effective_price);
            });

            // sortedTimes に沿って値を配列化（データなしは undefined、価格なしは null）
            const data = sortedTimes.map((time) => {
                const price = priceMap.get(time);
                // undefined の場合はデータなし → null に変換
                // null の場合は在庫なしで価格取得できず → グラフ上は null
                return price === undefined ? null : price;
            });

            // データポイント数に応じて点のサイズを調整
            const totalPoints = sortedTimes.length;
            const pointRadius = totalPoints > 50 ? 0 : totalPoints > 20 ? 2 : 3;

            return {
                label: store.store,
                data,
                borderColor: color.border,
                backgroundColor: color.border, // 凡例用（塗りつぶし四角）
                fill: false,
                tension: 0.3,
                pointRadius,
                pointHoverRadius: 5,
                spanGaps: true,
                // 選択された系列以外は非表示
                hidden: selectedLabel !== null && store.store !== selectedLabel,
            };
        });

        return { chartData: { labels, datasets }, sortedTimes };
    }, [stores, storeDefinitions, selectedLabel]);

    const options: ChartOptions<"line"> = useMemo(() => {
        // 全ストアの価格から min/max を計算（null は除外）
        const allPrices: number[] = [];
        stores.forEach((store) => {
            store.history.forEach((h) => {
                if (h.effective_price !== null) {
                    allPrices.push(h.effective_price);
                }
            });
        });

        // 全ストアで在庫なしの期間を検出し、annotation を生成
        const outOfStockPeriods = findOutOfStockPeriods(stores, sortedTimes);
        const annotations: Record<string, AnnotationOptions> = {};

        outOfStockPeriods.forEach((period, index) => {
            annotations[`outOfStock${index}`] = {
                type: "box",
                xMin: period.start - 0.5,
                xMax: period.end + 0.5,
                backgroundColor: "rgba(200, 200, 200, 0.3)",
                borderWidth: 0,
                label: {
                    display: period.end - period.start >= 2, // 3ポイント以上の期間のみラベル表示
                    content: "在庫なし",
                    position: "center",
                    color: "rgba(120, 120, 120, 0.8)",
                    font: { size: 9 },
                },
            };
        });

        // 価格データがない場合のデフォルト設定
        const minPrice = allPrices.length > 0 ? Math.min(...allPrices) : 0;
        const maxPrice = allPrices.length > 0 ? Math.max(...allPrices) : 100;
        const padding = (maxPrice - minPrice) * 0.1 || maxPrice * 0.1;

        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: "top" as const,
                    onClick: handleLegendClick,
                    labels: {
                        usePointStyle: true,
                        pointStyle: "rect",
                        boxWidth: largeLabels ? 14 : 10,
                        boxHeight: largeLabels ? 14 : 10,
                        padding: largeLabels ? 16 : 8,
                        font: { size: largeLabels ? 13 : 10 },
                        // 選択中の系列を強調（非選択は薄く）
                        generateLabels: (chart) => {
                            const datasets = chart.data.datasets;
                            return datasets.map((dataset, i) => ({
                                text: dataset.label || "",
                                fillStyle: dataset.backgroundColor as string,
                                strokeStyle: dataset.borderColor as string,
                                lineWidth: 1,
                                hidden: dataset.hidden,
                                index: i,
                                pointStyle: "rect" as const,
                                fontColor:
                                    selectedLabel !== null && dataset.label !== selectedLabel
                                        ? "rgba(128, 128, 128, 0.5)"
                                        : undefined,
                            }));
                        },
                    },
                },
                tooltip: {
                    titleFont: { size: largeLabels ? 13 : 11 },
                    bodyFont: { size: largeLabels ? 13 : 11 },
                    padding: largeLabels ? 10 : 6,
                    callbacks: {
                        title: (tooltipItems) => {
                            if (tooltipItems.length === 0) return "";
                            const index = tooltipItems[0].dataIndex;
                            const time = sortedTimes[index];
                            return time ? dayjs(time).format("YYYY年M月D日 H:00") : "";
                        },
                        label: (context) => {
                            const value = context.parsed.y;
                            const storeName = context.dataset.label || "";
                            return value !== null ? `${storeName}: ${formatPriceForChart(value, priceUnit)}` : "";
                        },
                    },
                },
                annotation: {
                    annotations,
                },
            },
            scales: {
                x: {
                    grid: {
                        display: false,
                    },
                    ticks: {
                        maxTicksLimit: 6,
                        font: { size: largeLabels ? 12 : 10 },
                        color: largeLabels ? "#4b5563" : undefined,
                    },
                },
                y: {
                    min: Math.max(0, minPrice - padding),
                    max: maxPrice + padding,
                    ticks: {
                        callback: (value) => formatPriceForYAxis(Number(value), priceUnit),
                        precision: 0,
                        font: { size: largeLabels ? 13 : 10 },
                        color: largeLabels ? "#374151" : undefined,
                    },
                },
            },
        };
    }, [stores, sortedTimes, selectedLabel, handleLegendClick, largeLabels]);

    // 有効な価格データがあるかチェック（履歴があっても全て null なら価格情報なし）
    const hasValidPriceData = stores.some((s) =>
        s.history.some((h) => h.effective_price !== null)
    );
    if (!hasValidPriceData) {
        // 「価格情報なし」を中央に表示
        return (
            <div className={`${className} relative flex items-center justify-center bg-gray-100 rounded`}>
                <span className="text-gray-500 text-sm">価格情報なし</span>
            </div>
        );
    }

    return (
        <div className={`${className} relative`}>
            {selectedLabel !== null && (
                <button
                    onClick={handleShowAll}
                    className="absolute top-0 right-0 z-10 px-2 py-1 text-xs bg-gray-100 hover:bg-gray-200 text-gray-600 rounded border border-gray-300 transition-colors"
                >
                    全て表示
                </button>
            )}
            <Line data={chartData} options={options} />
        </div>
    );
}
