import {
    CheckCircleIcon,
    XCircleIcon,
    ArrowTopRightOnSquareIcon,
    BuildingStorefrontIcon,
    PencilSquareIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";
import type { StoreEntry } from "../types";
import { formatPrice, formatPriceDiff } from "../utils/formatPrice";

interface StoreRowProps {
    store: StoreEntry;
    isBest: boolean;
    bestPrice: number | null;
    onEditClick?: (store: StoreEntry) => void;
}

export default function StoreRow({ store, isBest, bestPrice, onEditClick }: StoreRowProps) {
    const isInStock = store.stock > 0;
    const hasPrice = store.effective_price !== null;
    const priceDiff = hasPrice && bestPrice !== null ? store.effective_price! - bestPrice : 0;

    // メルカリの場合は product_url を優先、なければ url を使用
    const linkUrl = store.product_url || store.url;
    const hasValidUrl = Boolean(linkUrl);

    return (
        <div
            className={clsx(
                "flex items-center justify-between py-2 px-3 rounded-md",
                isBest && hasPrice ? "bg-blue-50 border border-blue-200" : "bg-gray-50"
            )}
        >
            <div className="flex items-center gap-2 min-w-0 flex-1">
                {hasValidUrl ? (
                    <a
                        href={linkUrl!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-gray-700 hover:text-blue-600 truncate flex items-center gap-1"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <BuildingStorefrontIcon className="h-3.5 w-3.5 flex-shrink-0" />
                        <span className="truncate">{store.store}</span>
                        <ArrowTopRightOnSquareIcon className="h-3 w-3 flex-shrink-0" />
                    </a>
                ) : (
                    <span className="text-xs text-gray-400 truncate flex items-center gap-1">
                        <BuildingStorefrontIcon className="h-3.5 w-3.5 flex-shrink-0" />
                        <span className="truncate">{store.store}</span>
                    </span>
                )}
                {isBest && hasPrice && (
                    <span className="text-xs px-1.5 py-0.5 bg-blue-100 text-blue-700 rounded whitespace-nowrap">
                        最安
                    </span>
                )}
            </div>
            <div className="flex items-center gap-2">
                <div className="text-right min-w-[5.5rem]">
                    {hasPrice ? (
                        <>
                            <div className="text-sm font-semibold text-gray-900 whitespace-nowrap tabular-nums">
                                {formatPrice(store.effective_price!, store.price_unit)}
                            </div>
                            {(priceDiff > 0 || store.point_rate > 0) && (
                                <div className="text-xs text-gray-400 whitespace-nowrap">
                                    {priceDiff > 0 && <span>{formatPriceDiff(priceDiff, store.price_unit)}</span>}
                                    {priceDiff > 0 && store.point_rate > 0 && <span> / </span>}
                                    {store.point_rate > 0 && <span>{store.point_rate}%還元考慮</span>}
                                </div>
                            )}
                        </>
                    ) : (
                        <div className="text-sm text-gray-400 whitespace-nowrap">---</div>
                    )}
                </div>
                <span
                    className={clsx(
                        "flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full flex-shrink-0",
                        isInStock ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                    )}
                >
                    {isInStock ? (
                        <CheckCircleIcon className="h-3 w-3" />
                    ) : (
                        <XCircleIcon className="h-3 w-3" />
                    )}
                </span>
                {onEditClick && (
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onEditClick(store);
                        }}
                        className="p-1 rounded-md hover:bg-gray-200 transition-colors cursor-pointer"
                        title="価格記録を編集"
                    >
                        <PencilSquareIcon className="h-4 w-4 text-gray-500" />
                    </button>
                )}
            </div>
        </div>
    );
}
