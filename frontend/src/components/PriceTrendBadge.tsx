import { memo } from "react";
import { ArrowTrendingDownIcon } from "@heroicons/react/24/solid";
import type { PriceTrend } from "../hooks/usePriceTrend";

interface PriceTrendBadgeProps {
    trend: PriceTrend;
    priceDropPercent?: number | null;
    compact?: boolean;
}

function PriceTrendBadge({ trend, priceDropPercent, compact = false }: PriceTrendBadgeProps) {
    // 上昇・安定トレンドの場合は何も表示しない
    if (trend !== "down" || priceDropPercent === null || priceDropPercent === undefined) {
        return null;
    }

    // 下落率に応じた表示を決定
    let label: string;
    let bgColor: string;
    let textColor: string;

    if (priceDropPercent >= 10) {
        // 10%以上の下落
        label = compact ? `-${Math.round(priceDropPercent)}%` : "大幅値下げ中!";
        bgColor = "bg-red-100";
        textColor = "text-red-700";
    } else if (priceDropPercent >= 5) {
        // 5%以上の下落
        label = compact ? `-${Math.round(priceDropPercent)}%` : "値下げ中!";
        bgColor = "bg-orange-100";
        textColor = "text-orange-700";
    } else {
        // 2%以上の下落
        label = compact ? `-${Math.round(priceDropPercent)}%` : "値下がり傾向";
        bgColor = "bg-amber-50";
        textColor = "text-amber-700";
    }

    return (
        <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${bgColor} ${textColor}`}
        >
            <ArrowTrendingDownIcon className="h-3 w-3" />
            {label}
        </span>
    );
}

export default memo(PriceTrendBadge);
