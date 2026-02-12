/**
 * PriceChart 共通ロジック
 *
 * このファイルは以下から使用されます：
 * - frontend/src/components/PriceChart.tsx (React フロントエンド)
 * - src/price_watch/templates/chart.html (Selenium 画像生成)
 *
 * 変更時は両方の動作を確認してください。
 */

// グローバルオブジェクトに登録
window.PriceChartCommon = (function () {
    "use strict";

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
     * @param {string} hex - Hex カラーコード (例: "#ff9900")
     * @returns {{r: number, g: number, b: number} | null}
     */
    function hexToRgb(hex) {
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
     * @param {string} storeName - ストア名
     * @param {Array<{name: string, color?: string}>} storeDefinitions - ストア定義
     * @param {number} fallbackIndex - フォールバック用インデックス
     * @returns {{border: string, bg: string}}
     */
    function getStoreColor(storeName, storeDefinitions, fallbackIndex) {
        const storeDef = storeDefinitions.find((s) => s.name === storeName);
        if (storeDef && storeDef.color) {
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
     * 価格をグラフのY軸ラベル用にフォーマット
     * @param {number} price - 価格
     * @param {string} priceUnit - 通貨単位 ("円", "ドル" など)
     * @returns {string}
     */
    function formatPriceForYAxis(price, priceUnit) {
        if (priceUnit === "円") {
            return "¥" + Math.round(price).toLocaleString();
        }
        if (priceUnit === "ドル") {
            return (
                "$" +
                price.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                })
            );
        }
        return (
            price.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }) + priceUnit
        );
    }

    /**
     * 価格をチャート表示用にフォーマット（ツールチップ用）
     * @param {number} price - 価格
     * @param {string} priceUnit - 通貨単位
     * @returns {string}
     */
    function formatPriceForChart(price, priceUnit) {
        if (priceUnit === "円") {
            return "¥" + price.toLocaleString();
        }
        if (priceUnit === "ドル") {
            return (
                "$" +
                price.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                })
            );
        }
        return (
            price.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }) + priceUnit
        );
    }

    /**
     * 全ストアで在庫なしの期間を検出
     * @param {Array} stores - ストアデータ配列
     * @param {Array<string>} sortedTimes - ソート済み時間配列
     * @param {function} dayjs - dayjs 関数
     * @returns {Array<{start: number, end: number}>}
     */
    function findOutOfStockPeriods(stores, sortedTimes, dayjs) {
        if (stores.length === 0 || sortedTimes.length === 0) {
            return [];
        }

        const periods = [];
        let periodStart = null;

        for (let i = 0; i < sortedTimes.length; i++) {
            const time = sortedTimes[i];
            const timeHour = dayjs(time).format("YYYY-MM-DD HH:00");

            let hasDataForTime = false;
            let anyInStock = false;

            for (const store of stores) {
                const historyItems = store.history.filter(
                    (h) => dayjs(h.time).format("YYYY-MM-DD HH:00") === timeHour
                );
                if (historyItems.length > 0) {
                    hasDataForTime = true;
                    if (historyItems.some((h) => h.stock !== 0)) {
                        anyInStock = true;
                        break;
                    }
                }
            }

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

        if (periodStart !== null) {
            periods.push({ start: periodStart, end: sortedTimes.length - 1 });
        }

        return periods;
    }

    /**
     * ラベルのフォーマット関数を生成
     * @param {Array<string>} allTimes - 全時間配列
     * @param {function} dayjs - dayjs 関数
     * @returns {function}
     */
    function createLabelFormatter(allTimes, dayjs) {
        const firstTime = dayjs(allTimes[0]);
        const lastTime = dayjs(allTimes[allTimes.length - 1]);
        const spanDays = lastTime.diff(firstTime, "day");

        return function (timeStr) {
            const time = dayjs(timeStr);
            if (spanDays <= 3) {
                return time.format("M月D日 H:mm");
            } else {
                return time.format("M月D日");
            }
        };
    }

    /**
     * チャートデータセットを作成
     * @param {Array} stores - ストアデータ配列
     * @param {Array} storeDefinitions - ストア定義配列
     * @param {Array<string>} sortedTimes - ソート済み時間配列
     * @param {function} getCurrencyRate - 通貨レート取得関数
     * @returns {Array} datasets
     */
    function createDatasets(stores, storeDefinitions, sortedTimes, getCurrencyRate) {
        return stores.map((store, index) => {
            const color = getStoreColor(store.store, storeDefinitions, index);
            const rate = getCurrencyRate ? getCurrencyRate(store.store) : store.currency_rate || 1.0;

            // 時間ごとの effective_price をマップ（円換算済み）
            const priceMap = new Map();
            store.history.forEach((h) => {
                const effectivePrice = h.effective_price !== undefined ? h.effective_price : h.price;
                if (effectivePrice !== null) {
                    const convertedPrice = Math.round(effectivePrice * rate);
                    priceMap.set(h.time, convertedPrice);
                }
            });

            // sortedTimes に沿って値を配列化
            const data = sortedTimes.map((time) => {
                const price = priceMap.get(time);
                return price === undefined ? null : price;
            });

            return {
                label: store.store,
                data: data,
                borderColor: color.border,
                backgroundColor: color.border,
                borderWidth: 3,
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 6,
                spanGaps: true,
            };
        });
    }

    /**
     * Y軸の範囲を計算
     * @param {Array} stores - ストアデータ配列
     * @param {function} getCurrencyRate - 通貨レート取得関数
     * @returns {{min: number, max: number, padding: number}}
     */
    function calculateYAxisRange(stores, getCurrencyRate) {
        const allPrices = [];
        stores.forEach((store) => {
            const rate = getCurrencyRate ? getCurrencyRate(store.store) : store.currency_rate || 1.0;
            store.history.forEach((h) => {
                const effectivePrice = h.effective_price !== undefined ? h.effective_price : h.price;
                if (effectivePrice !== null) {
                    allPrices.push(Math.round(effectivePrice * rate));
                }
            });
        });

        const minPrice = allPrices.length > 0 ? Math.min(...allPrices) : 0;
        const maxPrice = allPrices.length > 0 ? Math.max(...allPrices) : 100;
        const padding = (maxPrice - minPrice) * 0.1 || maxPrice * 0.1;

        return { min: minPrice, max: maxPrice, padding: padding };
    }

    /**
     * 在庫なし期間のアノテーションを生成
     * @param {Array<{start: number, end: number}>} outOfStockPeriods
     * @param {number} totalPoints
     * @returns {Object} annotations
     */
    function createOutOfStockAnnotations(outOfStockPeriods, totalPoints) {
        const annotations = {};
        outOfStockPeriods.forEach((period, index) => {
            const periodLength = period.end - period.start + 1;
            const isMoreThanHalf = periodLength > totalPoints / 2;
            annotations["outOfStock" + index] = {
                type: "box",
                xMin: period.start - 0.5,
                xMax: period.end + 0.5,
                backgroundColor: "rgba(200, 200, 200, 0.3)",
                borderWidth: 0,
                label: {
                    display: isMoreThanHalf,
                    content: "在庫なし",
                    position: "center",
                    color: "rgba(120, 120, 120, 0.8)",
                    font: { size: 9 },
                },
            };
        });
        return annotations;
    }

    /**
     * 静的チャート用のオプションを生成（画像生成用）
     * @param {Object} config
     * @returns {Object} Chart.js options
     */
    function createStaticChartOptions(config) {
        const { stores, sortedTimes, getCurrencyRate, priceUnit = "円", largeLabels = false, dayjs } = config;

        const { min: minPrice, max: maxPrice, padding } = calculateYAxisRange(stores, getCurrencyRate);
        const outOfStockPeriods = findOutOfStockPeriods(stores, sortedTimes, dayjs);
        const annotations = createOutOfStockAnnotations(outOfStockPeriods, sortedTimes.length);

        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: {
                mode: "index",
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    position: "top",
                    labels: {
                        usePointStyle: true,
                        pointStyle: "rect",
                        boxWidth: largeLabels ? 14 : 10,
                        boxHeight: largeLabels ? 14 : 10,
                        padding: largeLabels ? 16 : 8,
                        font: { size: largeLabels ? 13 : 10 },
                        color: "#000",
                    },
                },
                tooltip: {
                    enabled: false,
                },
                annotation: {
                    annotations: annotations,
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
                        color: "#666",
                    },
                },
                y: {
                    min: Math.max(0, minPrice - padding),
                    max: maxPrice + padding,
                    ticks: {
                        callback: function (value) {
                            return formatPriceForYAxis(Number(value), priceUnit);
                        },
                        precision: 0,
                        font: { size: largeLabels ? 13 : 10 },
                        color: "#666",
                    },
                },
            },
        };
    }

    // 公開 API
    return {
        DEFAULT_COLORS: DEFAULT_COLORS,
        hexToRgb: hexToRgb,
        getStoreColor: getStoreColor,
        formatPriceForYAxis: formatPriceForYAxis,
        formatPriceForChart: formatPriceForChart,
        findOutOfStockPeriods: findOutOfStockPeriods,
        createLabelFormatter: createLabelFormatter,
        createDatasets: createDatasets,
        calculateYAxisRange: calculateYAxisRange,
        createOutOfStockAnnotations: createOutOfStockAnnotations,
        createStaticChartOptions: createStaticChartOptions,
    };
})();
