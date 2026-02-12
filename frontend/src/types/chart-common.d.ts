/**
 * chart-common.js の型定義
 */

interface RgbColor {
    r: number;
    g: number;
    b: number;
}

interface ChartColor {
    border: string;
    bg: string;
}

interface StoreDefinitionForChart {
    name: string;
    color?: string | null;
}

interface OutOfStockPeriod {
    start: number;
    end: number;
}

interface YAxisRange {
    min: number;
    max: number;
    padding: number;
}

interface StaticChartOptionsConfig {
    stores: Array<{
        store: string;
        history: Array<{
            time: string;
            effective_price?: number | null;
            price?: number | null;
            stock?: number;
        }>;
        currency_rate?: number;
    }>;
    sortedTimes: string[];
    getCurrencyRate?: (storeName: string) => number;
    priceUnit?: string;
    largeLabels?: boolean;
    dayjs: typeof import("dayjs").default;
}

interface PriceChartCommon {
    DEFAULT_COLORS: ChartColor[];
    hexToRgb: (hex: string) => RgbColor | null;
    getStoreColor: (
        storeName: string,
        storeDefinitions: StoreDefinitionForChart[],
        fallbackIndex: number
    ) => ChartColor;
    formatPriceForYAxis: (price: number, priceUnit: string) => string;
    formatPriceForChart: (price: number, priceUnit: string) => string;
    findOutOfStockPeriods: (
        stores: StaticChartOptionsConfig["stores"],
        sortedTimes: string[],
        dayjs: typeof import("dayjs").default
    ) => OutOfStockPeriod[];
    createLabelFormatter: (
        allTimes: string[],
        dayjs: typeof import("dayjs").default
    ) => (timeStr: string) => string;
    createDatasets: (
        stores: StaticChartOptionsConfig["stores"],
        storeDefinitions: StoreDefinitionForChart[],
        sortedTimes: string[],
        getCurrencyRate?: (storeName: string) => number
    ) => Array<{
        label: string;
        data: (number | null)[];
        borderColor: string;
        backgroundColor: string;
        fill: boolean;
        tension: number;
        pointRadius: number;
        pointHoverRadius: number;
        spanGaps: boolean;
    }>;
    calculateYAxisRange: (
        stores: StaticChartOptionsConfig["stores"],
        getCurrencyRate?: (storeName: string) => number
    ) => YAxisRange;
    createOutOfStockAnnotations: (
        outOfStockPeriods: OutOfStockPeriod[],
        totalPoints: number
    ) => Record<string, unknown>;
    createStaticChartOptions: (config: StaticChartOptionsConfig) => unknown;
}

declare global {
    interface Window {
        PriceChartCommon: PriceChartCommon;
    }
}

export {};
