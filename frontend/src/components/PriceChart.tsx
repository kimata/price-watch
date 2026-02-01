import { useMemo, useState, useCallback, useRef, memo } from "react";

// カスタムツールチップポジショナーの型宣言
declare module "chart.js" {
    interface TooltipPositionerMap {
        fixedBottom: TooltipPositionerFunction<ChartType>;
    }
}
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
import type { ChartOptions, LegendItem, ChartEvent, Chart, Plugin, ChartType, TooltipPositionerFunction } from "chart.js";
import annotationPlugin from "chartjs-plugin-annotation";
import type { AnnotationOptions } from "chartjs-plugin-annotation";
import dayjs from "dayjs";
import type { StoreEntry, StoreDefinition } from "../types";
import { formatPriceForChart, formatPriceForYAxis } from "../utils/formatPrice";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler, annotationPlugin);

// カスタムツールチップポジショナーを登録（縦線の位置にキャレットを向ける）
Tooltip.positioners.fixedBottom = function (elements, _eventPosition) {
    if (!elements.length) {
        return false;
    }

    const chart = this.chart;
    const chartArea = chart.chartArea;

    // データポイントの x 座標（縦線の位置）を取得
    const dataPointX = elements[0].element.x;

    // キャレットが縦線を指すように、データポイントの位置を返す
    // y は下部に固定
    return {
        x: dataPointX,
        y: chartArea.bottom - 10,
    };
};

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
        const timeHour = dayjs(time).format("YYYY-MM-DD HH:00");

        // この時間でデータがあるストアのうち、全て在庫なしかどうかをチェック
        let hasDataForTime = false;
        let anyInStock = false;

        for (const store of stores) {
            // 同じ時間帯の全てのエントリをチェック（1つでも在庫ありなら在庫ありとみなす）
            const historyItems = store.history.filter(
                (h) => dayjs(h.time).format("YYYY-MM-DD HH:00") === timeHour
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

/**
 * 各ストアのデータポイント（正確な時刻と価格のマッピング）
 */
interface StoreDataPoint {
    storeName: string;
    time: string; // ISO 8601 形式
    timestamp: number; // Unix timestamp (ms)
    effectivePrice: number | null;
}

/**
 * 二分探索で指定時刻以前の最も近いデータポイントを検索
 */
function findNearestPastPoint(
    sortedPoints: StoreDataPoint[],
    targetTimestamp: number
): StoreDataPoint | null {
    if (sortedPoints.length === 0) return null;

    let left = 0;
    let right = sortedPoints.length - 1;
    let result: StoreDataPoint | null = null;

    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        if (sortedPoints[mid].timestamp <= targetTimestamp) {
            result = sortedPoints[mid];
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }

    return result;
}

/**
 * ツールチップに表示するデータを構築
 */
interface TooltipData {
    baseTime: string; // 基準時刻（表示用）
    entries: Array<{
        storeName: string;
        effectivePrice: number | null;
        color: string;
        hasData: boolean; // interval 以内にデータがあるか
    }>;
}

/**
 * 縦線描画用のプラグイン
 * マウス位置に基づいて選択されたデータポイントの位置に縦線を描画
 */
const verticalLinePlugin: Plugin<"line"> = {
    id: "verticalLine",
    afterDraw: (chart) => {
        const tooltip = chart.tooltip;
        if (!tooltip || !tooltip.getActiveElements().length) {
            return;
        }

        const activeElements = tooltip.getActiveElements();
        if (activeElements.length === 0) return;

        const { ctx, chartArea } = chart;
        const x = activeElements[0].element.x;

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.lineWidth = 1;
        ctx.strokeStyle = "rgba(100, 100, 100, 0.5)";
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();
    },
};

interface PriceChartProps {
    stores: StoreEntry[];
    storeDefinitions: StoreDefinition[];
    className?: string;
    period?: string; // "30", "90", "180", "365", "all"
    largeLabels?: boolean; // 個別ページ用の大きめラベル
    checkIntervalSec?: number; // 監視間隔（秒）- ツールチップ表示用
}

function PriceChart({
    stores,
    storeDefinitions,
    className = "h-40",
    period: _period = "30",
    largeLabels = false,
    checkIntervalSec = 1800,
}: PriceChartProps) {
    // 選択された系列（null の場合は全て表示）
    const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
    const chartRef = useRef<Chart<"line"> | null>(null);
    const tooltipRef = useRef<HTMLDivElement | null>(null);

    // チャートでは常に円表示（異なる通貨のストアも円換算して比較可能にする）
    const priceUnit = "円";

    // ストア名 → 通貨換算レートのマッピングを作成
    const currencyRateMap = useMemo(() => {
        const map = new Map<string, number>();
        storeDefinitions.forEach((def) => {
            map.set(def.name, def.currency_rate);
        });
        return map;
    }, [storeDefinitions]);

    // ストアの通貨換算レートを取得
    const getCurrencyRate = useCallback(
        (storeName: string): number => {
            return currencyRateMap.get(storeName) ?? 1.0;
        },
        [currencyRateMap]
    );

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

    // 各ストアのデータポイントを正確な時刻で構築（円換算済み）
    const storeDataPoints = useMemo(() => {
        const result: Map<string, StoreDataPoint[]> = new Map();

        stores.forEach((store) => {
            const rate = getCurrencyRate(store.store);
            const points: StoreDataPoint[] = store.history
                .map((h) => ({
                    storeName: store.store,
                    time: h.time,
                    timestamp: dayjs(h.time).valueOf(),
                    // 円換算
                    effectivePrice: h.effective_price !== null ? Math.round(h.effective_price * rate) : null,
                }))
                .sort((a, b) => a.timestamp - b.timestamp);

            result.set(store.store, points);
        });

        return result;
    }, [stores, getCurrencyRate]);

    const { chartData, sortedTimes } = useMemo(() => {
        // 全ストアの履歴から日時を抽出してマージ（正確な時刻を保持）
        const allTimes = new Set<string>();
        stores.forEach((store) => {
            store.history.forEach((h) => {
                allTimes.add(h.time);
            });
        });

        // 現在時刻も追加（グラフの終点を現在時刻にする）
        const now = dayjs();
        allTimes.add(now.toISOString());

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
            const rate = getCurrencyRate(store.store);

            // 時間ごとの effective_price をマップ（正確な時刻で、円換算済み）
            const priceMap = new Map<string, number | null>();
            store.history.forEach((h) => {
                // 円換算
                const convertedPrice = h.effective_price !== null ? Math.round(h.effective_price * rate) : null;
                priceMap.set(h.time, convertedPrice);
            });

            // sortedTimes に沿って値を配列化（データなしは undefined、価格なしは null）
            const data = sortedTimes.map((time) => {
                const price = priceMap.get(time);
                // undefined の場合はデータなし → null に変換
                // null の場合は在庫なしで価格取得できず → グラフ上は null
                return price === undefined ? null : price;
            });

            return {
                label: store.store,
                data,
                borderColor: color.border,
                backgroundColor: color.border, // 凡例用（塗りつぶし四角）
                fill: false,
                tension: 0.3,
                pointRadius: 0, // 普段は点を非表示
                pointHoverRadius: 6, // ホバー時に点を表示
                spanGaps: true,
                // 選択された系列以外は非表示
                hidden: selectedLabel !== null && store.store !== selectedLabel,
            };
        });

        return { chartData: { labels, datasets }, sortedTimes };
    }, [stores, storeDefinitions, selectedLabel, getCurrencyRate]);

    /**
     * ツールチップデータを計算
     * マウス位置の時間から各ストアの最近傍データを検索
     */
    const calculateTooltipData = useCallback(
        (mouseTimestamp: number): TooltipData | null => {
            // 各ストアで最も近い過去のデータポイントを検索
            let basePoint: StoreDataPoint | null = null;

            for (const [, points] of storeDataPoints) {
                const point = findNearestPastPoint(points, mouseTimestamp);
                if (point) {
                    if (!basePoint || point.timestamp > basePoint.timestamp) {
                        basePoint = point;
                    }
                }
            }

            if (!basePoint) return null;

            const intervalMs = checkIntervalSec * 1000;
            const entries: TooltipData["entries"] = [];

            // 各ストアについて、基準時刻から interval 以内のデータを検索
            stores.forEach((store, index) => {
                const points = storeDataPoints.get(store.store) || [];
                const color = getStoreColor(store.store, storeDefinitions, index);

                // 基準時刻から interval 以内で最も近いデータを探す
                let nearestPoint: StoreDataPoint | null = null;
                let minDistance = Infinity;

                for (const point of points) {
                    const distance = Math.abs(point.timestamp - basePoint!.timestamp);
                    if (distance <= intervalMs && distance < minDistance) {
                        minDistance = distance;
                        nearestPoint = point;
                    }
                }

                entries.push({
                    storeName: store.store,
                    effectivePrice: nearestPoint?.effectivePrice ?? null,
                    color: color.border,
                    hasData: nearestPoint !== null,
                });
            });

            return {
                baseTime: basePoint.time,
                entries,
            };
        },
        [storeDataPoints, stores, storeDefinitions, checkIntervalSec]
    );

    /**
     * 外部 HTML ツールチップのハンドラ
     */
    const externalTooltipHandler = useCallback(
        (context: { chart: Chart; tooltip: { opacity: number; dataPoints?: Array<{ dataIndex: number }> } }) => {
            const { chart, tooltip } = context;
            const tooltipEl = tooltipRef.current;
            if (!tooltipEl) return;

            // ツールチップを非表示
            if (tooltip.opacity === 0) {
                tooltipEl.style.opacity = "0";
                return;
            }

            // データがない場合
            if (!tooltip.dataPoints || tooltip.dataPoints.length === 0) {
                tooltipEl.style.opacity = "0";
                return;
            }

            const dataIndex = tooltip.dataPoints[0].dataIndex;
            const time = sortedTimes[dataIndex];
            if (!time) {
                tooltipEl.style.opacity = "0";
                return;
            }

            const mouseTimestamp = dayjs(time).valueOf();
            const tooltipData = calculateTooltipData(mouseTimestamp);
            if (!tooltipData) {
                tooltipEl.style.opacity = "0";
                return;
            }

            // 最安価格を特定
            const validPrices = tooltipData.entries
                .filter((e) => e.hasData && e.effectivePrice !== null)
                .map((e) => e.effectivePrice as number);
            const lowestPrice = validPrices.length > 0 ? Math.min(...validPrices) : null;

            // 価格の安い順にソート
            const sortedEntries = [...tooltipData.entries].sort((a, b) => {
                if (!a.hasData && !b.hasData) return 0;
                if (!a.hasData) return 1;
                if (!b.hasData) return -1;
                if (a.effectivePrice === null && b.effectivePrice === null) return 0;
                if (a.effectivePrice === null) return 1;
                if (b.effectivePrice === null) return -1;
                return a.effectivePrice - b.effectivePrice;
            });

            // HTML を構築
            const titleHtml = `<div style="font-weight: bold; margin-bottom: 4px; font-size: ${largeLabels ? "13px" : "11px"};">${dayjs(tooltipData.baseTime).format("YYYY年M月D日 H:mm")}</div>`;

            const rowsHtml = sortedEntries
                .map((entry) => {
                    let priceText: string;
                    if (!entry.hasData) {
                        priceText = "-";
                    } else if (entry.effectivePrice === null) {
                        priceText = "在庫なし";
                    } else if (lowestPrice !== null && entry.effectivePrice === lowestPrice) {
                        priceText = formatPriceForChart(entry.effectivePrice, priceUnit);
                    } else {
                        const diff = lowestPrice !== null ? entry.effectivePrice - lowestPrice : 0;
                        priceText = `+${formatPriceForChart(diff, priceUnit)}`;
                    }
                    return `<div style="display: flex; justify-content: space-between; gap: 12px; font-size: ${largeLabels ? "12px" : "10px"};">
                        <span>${entry.storeName}</span>
                        <span style="text-align: right;">${priceText}</span>
                    </div>`;
                })
                .join("");

            tooltipEl.innerHTML = titleHtml + rowsHtml;

            // 位置を計算
            const chartArea = chart.chartArea;
            const dataPointX = chart.tooltip?.caretX ?? 0;
            const chartCenterX = (chartArea.left + chartArea.right) / 2;

            // ツールチップの幅を取得
            tooltipEl.style.opacity = "1";
            tooltipEl.style.visibility = "hidden";
            tooltipEl.style.display = "block";
            const tooltipWidth = tooltipEl.offsetWidth;
            tooltipEl.style.visibility = "visible";

            // 縦線の左右どちらに表示するか決定
            const offset = 12;
            let left: number;
            if (dataPointX < chartCenterX) {
                // 左側にカーソル → 右側にツールチップ
                left = dataPointX + offset;
            } else {
                // 右側にカーソル → 左側にツールチップ
                left = dataPointX - tooltipWidth - offset;
            }

            tooltipEl.style.left = `${left}px`;
            tooltipEl.style.top = `${chartArea.bottom - 10}px`;
            tooltipEl.style.transform = "translateY(-100%)";
        },
        [sortedTimes, calculateTooltipData, largeLabels, priceUnit]
    );

    const options: ChartOptions<"line"> = useMemo(() => {
        // 全ストアの価格から min/max を計算（null は除外、円換算済み）
        const allPrices: number[] = [];
        stores.forEach((store) => {
            const rate = getCurrencyRate(store.store);
            store.history.forEach((h) => {
                if (h.effective_price !== null) {
                    allPrices.push(Math.round(h.effective_price * rate));
                }
            });
        });

        // 全ストアで在庫なしの期間を検出し、annotation を生成
        const outOfStockPeriods = findOutOfStockPeriods(stores, sortedTimes);
        const annotations: Record<string, AnnotationOptions> = {};

        const totalPoints = sortedTimes.length;
        outOfStockPeriods.forEach((period, index) => {
            const periodLength = period.end - period.start + 1;
            const isMoreThanHalf = periodLength > totalPoints / 2;
            annotations[`outOfStock${index}`] = {
                type: "box",
                xMin: period.start - 0.5,
                xMax: period.end + 0.5,
                backgroundColor: "rgba(200, 200, 200, 0.3)",
                borderWidth: 0,
                label: {
                    display: isMoreThanHalf, // 全期間の半分以上の場合のみラベル表示
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
            animation: false, // ちらつき抑制のためアニメーションを無効化
            interaction: {
                mode: "index",
                intersect: false,
            },
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
                    enabled: false, // 組み込みツールチップを無効化
                    external: externalTooltipHandler,
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
    }, [
        stores,
        sortedTimes,
        selectedLabel,
        handleLegendClick,
        largeLabels,
        priceUnit,
        externalTooltipHandler,
        getCurrencyRate,
    ]);

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
            <Line ref={chartRef} data={chartData} options={options} plugins={[verticalLinePlugin]} />
            {/* カスタム HTML ツールチップ */}
            <div
                ref={tooltipRef}
                style={{
                    position: "absolute",
                    opacity: 0,
                    pointerEvents: "none",
                    backgroundColor: "rgba(0, 0, 0, 0.8)",
                    color: "white",
                    borderRadius: "4px",
                    padding: "8px 12px",
                    whiteSpace: "nowrap",
                    zIndex: 100,
                    transition: "opacity 0.1s ease",
                }}
            />
        </div>
    );
}

export default memo(PriceChart, (prev, next) => {
    // ストアと期間で比較
    if (prev.period !== next.period) return false;
    if (prev.largeLabels !== next.largeLabels) return false;
    if (prev.checkIntervalSec !== next.checkIntervalSec) return false;
    if (prev.className !== next.className) return false;

    // ストアの履歴データで変更を検出
    if (prev.stores.length !== next.stores.length) return false;

    for (let i = 0; i < prev.stores.length; i++) {
        const prevStore = prev.stores[i];
        const nextStore = next.stores[i];
        if (prevStore.store !== nextStore.store) return false;
        if (prevStore.history.length !== nextStore.history.length) return false;
        // 最新の履歴エントリのみ比較（完全比較は重いため）
        const prevLast = prevStore.history[prevStore.history.length - 1];
        const nextLast = nextStore.history[nextStore.history.length - 1];
        if (prevLast?.time !== nextLast?.time) return false;
        if (prevLast?.effective_price !== nextLast?.effective_price) return false;
    }

    return true;
});
