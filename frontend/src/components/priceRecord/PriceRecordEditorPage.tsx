import { useState, useEffect, useCallback, useMemo } from "react";
import { ArrowLeftIcon, ArrowPathIcon, TrashIcon, FunnelIcon } from "@heroicons/react/24/outline";
import type { Item, StoreEntry } from "../../types";
import { fetchPriceRecords, type PriceRecord, type ItemInfo } from "../../services/priceRecordService";
import { useToast } from "../../contexts/ToastContext";
import LoadingSpinner from "../LoadingSpinner";
import PriceRecordTable from "./PriceRecordTable";
import DeleteConfirmModal from "./DeleteConfirmModal";
import { formatPrice } from "../../utils/formatPrice";

interface PriceRecordEditorPageProps {
    item: Item;
    store: StoreEntry;
    onBack: () => void;
}

export default function PriceRecordEditorPage({
    item,
    store,
    onBack,
}: PriceRecordEditorPageProps) {
    const { showToast } = useToast();
    const [loading, setLoading] = useState(true);
    const [itemInfo, setItemInfo] = useState<ItemInfo | null>(null);
    const [records, setRecords] = useState<PriceRecord[]>([]);
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
    const [requirePassword, setRequirePassword] = useState(false);
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [priceThreshold, setPriceThreshold] = useState<string>("");

    // 記録を読み込み
    const loadRecords = useCallback(async () => {
        setLoading(true);
        try {
            const response = await fetchPriceRecords(store.item_key);
            setItemInfo(response.item);
            setRecords(response.records);
            setRequirePassword(response.require_password);
            setSelectedIds(new Set());
        } catch (error) {
            console.error("Failed to load records:", error);
            showToast("価格記録の読み込みに失敗しました", "error");
        } finally {
            setLoading(false);
        }
    }, [store.item_key, showToast]);

    useEffect(() => {
        loadRecords();
    }, [loadRecords]);

    // 閾値以下の価格を持つレコードを選択
    const handleSelectByThreshold = useCallback(() => {
        const threshold = parseInt(priceThreshold, 10);
        if (isNaN(threshold) || threshold <= 0) {
            showToast("有効な価格を入力してください", "error");
            return;
        }

        const newSelected = new Set<number>();
        records.forEach((record) => {
            if (record.price !== null && record.price < threshold) {
                newSelected.add(record.id);
            }
        });

        if (newSelected.size === 0) {
            showToast("該当するレコードがありません", "info");
        } else {
            setSelectedIds(newSelected);
            showToast(`${newSelected.size}件のレコードを選択しました`, "info");
        }
    }, [priceThreshold, records, showToast]);

    // 選択状態の切り替え
    const handleToggleSelect = useCallback((id: number) => {
        setSelectedIds((prev) => {
            const newSet = new Set(prev);
            if (newSet.has(id)) {
                newSet.delete(id);
            } else {
                newSet.add(id);
            }
            return newSet;
        });
    }, []);

    // 全選択/全解除
    const handleToggleAll = useCallback(() => {
        if (selectedIds.size === records.length) {
            setSelectedIds(new Set());
        } else {
            setSelectedIds(new Set(records.map((r) => r.id)));
        }
    }, [records, selectedIds.size]);

    // 削除完了後のハンドラ
    const handleDeleteComplete = useCallback(() => {
        setShowDeleteModal(false);
        loadRecords();
    }, [loadRecords]);

    // 統計情報
    const stats = useMemo(() => {
        const validPrices = records.filter((r) => r.price !== null).map((r) => r.price as number);
        const selectedPrices = records
            .filter((r) => selectedIds.has(r.id) && r.price !== null)
            .map((r) => r.price as number);

        return {
            totalCount: records.length,
            selectedCount: selectedIds.size,
            lowestPrice: validPrices.length > 0 ? Math.min(...validPrices) : null,
            highestPrice: validPrices.length > 0 ? Math.max(...validPrices) : null,
            selectedLowest: selectedPrices.length > 0 ? Math.min(...selectedPrices) : null,
            selectedHighest: selectedPrices.length > 0 ? Math.max(...selectedPrices) : null,
        };
    }, [records, selectedIds]);

    const priceUnit = itemInfo?.price_unit ?? "円";

    return (
        <div className="min-h-screen bg-gray-100">
            {/* ヘッダー */}
            <header className="bg-white shadow-sm sticky top-0 z-10">
                <div className="max-w-4xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={onBack}
                                className="p-2 rounded-md hover:bg-gray-100 transition-colors cursor-pointer"
                                title="戻る"
                            >
                                <ArrowLeftIcon className="w-5 h-5 text-gray-600" />
                            </button>
                            <div>
                                <h1 className="text-lg font-semibold text-gray-900">
                                    価格記録編集
                                </h1>
                                <p className="text-sm text-gray-500">
                                    {item.name} - {store.store}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={loadRecords}
                                disabled={loading}
                                className="p-2 rounded-md hover:bg-gray-100 transition-colors disabled:opacity-50 cursor-pointer"
                                title="再読み込み"
                            >
                                <ArrowPathIcon className={`w-5 h-5 text-gray-600 ${loading ? "animate-spin" : ""}`} />
                            </button>
                            <button
                                onClick={() => setShowDeleteModal(true)}
                                disabled={selectedIds.size === 0}
                                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                            >
                                <TrashIcon className="w-4 h-4" />
                                削除 ({selectedIds.size})
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            <main className="max-w-4xl mx-auto px-4 py-6">
                {loading ? (
                    <div className="flex justify-center py-12">
                        <LoadingSpinner />
                    </div>
                ) : (
                    <>
                        {/* 統計情報 */}
                        <div className="bg-white rounded-lg shadow-md border border-gray-200 p-4 mb-4">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                    <span className="text-gray-500">全レコード数:</span>{" "}
                                    <span className="font-medium">{stats.totalCount}</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">選択中:</span>{" "}
                                    <span className="font-medium text-red-600">{stats.selectedCount}</span>
                                </div>
                                <div>
                                    <span className="text-gray-500">最安値:</span>{" "}
                                    <span className="font-medium">
                                        {stats.lowestPrice !== null ? formatPrice(stats.lowestPrice, priceUnit) : "-"}
                                    </span>
                                </div>
                                <div>
                                    <span className="text-gray-500">最高値:</span>{" "}
                                    <span className="font-medium">
                                        {stats.highestPrice !== null ? formatPrice(stats.highestPrice, priceUnit) : "-"}
                                    </span>
                                </div>
                            </div>
                            {stats.selectedCount > 0 && (
                                <div className="mt-2 pt-2 border-t border-gray-100 text-sm text-red-600">
                                    選択中のレコード: 価格範囲{" "}
                                    {stats.selectedLowest !== null ? formatPrice(stats.selectedLowest, priceUnit) : "-"} 〜{" "}
                                    {stats.selectedHighest !== null ? formatPrice(stats.selectedHighest, priceUnit) : "-"}
                                </div>
                            )}
                        </div>

                        {/* フィルタ */}
                        <div className="bg-white rounded-lg shadow-md border border-gray-200 p-4 mb-4">
                            <div className="flex items-center gap-3">
                                <FunnelIcon className="w-5 h-5 text-gray-500" />
                                <span className="text-sm text-gray-600">価格閾値:</span>
                                <input
                                    type="number"
                                    value={priceThreshold}
                                    onChange={(e) => setPriceThreshold(e.target.value)}
                                    placeholder="例: 1000"
                                    className="w-32 px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                                />
                                <span className="text-sm text-gray-500">{priceUnit}未満を選択</span>
                                <button
                                    onClick={handleSelectByThreshold}
                                    className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md transition-colors cursor-pointer"
                                >
                                    一括選択
                                </button>
                            </div>
                        </div>

                        {/* テーブル */}
                        <div className="bg-white rounded-lg shadow-md border border-gray-200">
                            <PriceRecordTable
                                records={records}
                                selectedIds={selectedIds}
                                onToggleSelect={handleToggleSelect}
                                onToggleAll={handleToggleAll}
                                priceUnit={priceUnit}
                            />
                        </div>

                        {records.length === 0 && (
                            <div className="text-center py-8 text-gray-500">
                                価格記録がありません
                            </div>
                        )}
                    </>
                )}
            </main>

            {/* 削除確認モーダル */}
            {showDeleteModal && itemInfo && (
                <DeleteConfirmModal
                    itemKey={store.item_key}
                    recordIds={Array.from(selectedIds)}
                    requirePassword={requirePassword}
                    priceUnit={priceUnit}
                    onConfirm={handleDeleteComplete}
                    onCancel={() => setShowDeleteModal(false)}
                />
            )}
        </div>
    );
}
