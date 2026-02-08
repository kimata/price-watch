import { useMemo } from "react";
import type { PriceHistoryPoint } from "../types";

export type PriceTrend = "up" | "down" | "stable";

interface PriceTrendResult {
    trend: PriceTrend;
    priceDropPercent: number | null;
}

// 過去7日間の価格変動を分析
export function usePriceTrend(history: PriceHistoryPoint[]): PriceTrendResult {
    return useMemo(() => {
        if (history.length < 2) {
            return { trend: "stable", priceDropPercent: null };
        }

        // 有効な価格データのみを抽出（null除外）
        const validPrices = history.filter((h) => h.effective_price !== null);
        if (validPrices.length < 2) {
            return { trend: "stable", priceDropPercent: null };
        }

        // 時系列でソート（古い順）
        const sorted = [...validPrices].sort(
            (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
        );

        // 最新価格
        const latestPrice = sorted[sorted.length - 1].effective_price!;

        // 7日前の価格を探す（7日以内で最も古いデータ）
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

        let oldestValidPrice: number | null = null;
        for (const point of sorted) {
            const pointDate = new Date(point.time);
            if (pointDate >= sevenDaysAgo && point.effective_price !== null) {
                oldestValidPrice = point.effective_price;
                break;
            }
        }

        // 7日以内のデータがない場合は最初のデータを使用
        if (oldestValidPrice === null) {
            oldestValidPrice = sorted[0].effective_price!;
        }

        // 価格変動率を計算
        const priceDiff = latestPrice - oldestValidPrice;
        const priceChangePercent = (priceDiff / oldestValidPrice) * 100;

        // トレンドを判定（2%以上の変動をトレンドとして扱う）
        let trend: PriceTrend;
        if (priceChangePercent <= -2) {
            trend = "down";
        } else if (priceChangePercent >= 2) {
            trend = "up";
        } else {
            trend = "stable";
        }

        // 下落率（絶対値）
        const priceDropPercent = trend === "down" ? Math.abs(priceChangePercent) : null;

        return { trend, priceDropPercent };
    }, [history]);
}
