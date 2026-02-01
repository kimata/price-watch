import { useMemo } from "react";
import dayjs from "dayjs";
import type { PriceRecord } from "../../services/priceRecordService";
import { formatPrice } from "../../utils/formatPrice";

interface PriceRecordTableProps {
    records: PriceRecord[];
    selectedIds: Set<number>;
    onToggleSelect: (id: number) => void;
    onToggleAll: () => void;
    priceUnit: string;
}

// 在庫状態を表示用に変換
function getStockLabel(stock: number | null): { label: string; className: string } {
    if (stock === null) {
        return { label: "不明", className: "text-gray-400" };
    }
    if (stock === 1) {
        return { label: "在庫あり", className: "text-green-600" };
    }
    return { label: "在庫なし", className: "text-red-600" };
}

// クロールステータスを表示用に変換
function getCrawlStatusLabel(status: number): { label: string; className: string } {
    if (status === 1) {
        return { label: "成功", className: "text-green-600" };
    }
    return { label: "失敗", className: "text-red-600" };
}

export default function PriceRecordTable({
    records,
    selectedIds,
    onToggleSelect,
    onToggleAll,
    priceUnit,
}: PriceRecordTableProps) {
    const allSelected = useMemo(() => {
        return records.length > 0 && selectedIds.size === records.length;
    }, [records.length, selectedIds.size]);

    const someSelected = useMemo(() => {
        return selectedIds.size > 0 && selectedIds.size < records.length;
    }, [records.length, selectedIds.size]);

    if (records.length === 0) {
        return null;
    }

    return (
        <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                    <tr>
                        <th className="w-12 px-4 py-3">
                            <input
                                type="checkbox"
                                checked={allSelected}
                                ref={(el) => {
                                    if (el) el.indeterminate = someSelected;
                                }}
                                onChange={onToggleAll}
                                className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 cursor-pointer"
                            />
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                            日時
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                            価格
                        </th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                            在庫
                        </th>
                        <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                            取得
                        </th>
                    </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                    {records.map((record) => {
                        const isSelected = selectedIds.has(record.id);
                        const stockInfo = getStockLabel(record.stock);
                        const crawlInfo = getCrawlStatusLabel(record.crawl_status);

                        return (
                            <tr
                                key={record.id}
                                className={`${isSelected ? "bg-red-50" : "hover:bg-gray-50"} cursor-pointer transition-colors`}
                                onClick={() => onToggleSelect(record.id)}
                            >
                                <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                                    <input
                                        type="checkbox"
                                        checked={isSelected}
                                        onChange={() => onToggleSelect(record.id)}
                                        className="h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 cursor-pointer"
                                    />
                                </td>
                                <td className="px-4 py-3 text-sm text-gray-900 whitespace-nowrap">
                                    {dayjs(record.time).format("YYYY/MM/DD HH:mm")}
                                </td>
                                <td className="px-4 py-3 text-sm text-right font-medium whitespace-nowrap">
                                    {record.price !== null ? (
                                        <span className={isSelected ? "text-red-600" : "text-gray-900"}>
                                            {formatPrice(record.price, priceUnit)}
                                        </span>
                                    ) : (
                                        <span className="text-gray-400">-</span>
                                    )}
                                </td>
                                <td className="px-4 py-3 text-sm text-center whitespace-nowrap">
                                    <span className={stockInfo.className}>{stockInfo.label}</span>
                                </td>
                                <td className="px-4 py-3 text-sm text-center whitespace-nowrap">
                                    <span className={crawlInfo.className}>{crawlInfo.label}</span>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
