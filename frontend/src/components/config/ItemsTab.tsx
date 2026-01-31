import { useState, useCallback, useMemo } from "react";
import { PlusIcon, PencilIcon, TrashIcon, MagnifyingGlassIcon } from "@heroicons/react/24/outline";
import type { TargetConfig, ItemDefinitionConfig } from "../../types/config";
import { DEFAULT_ITEM_DEFINITION } from "../../types/config";
import ItemForm from "./ItemForm";

interface ItemsTabProps {
    config: TargetConfig;
    onChange: (config: TargetConfig) => void;
}

export default function ItemsTab({ config, onChange }: ItemsTabProps) {
    const [editingItem, setEditingItem] = useState<ItemDefinitionConfig | null>(null);
    const [editingIndex, setEditingIndex] = useState<number | null>(null);
    const [isCreating, setIsCreating] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [categoryFilter, setCategoryFilter] = useState<string>("");

    // ユニークなカテゴリー一覧（フィルター用）
    const availableCategories = useMemo(() => {
        const categories = new Set<string>();
        config.item_list.forEach((item) => {
            categories.add(item.category || "その他");
        });
        return ["", ...Array.from(categories).sort()];
    }, [config.item_list]);

    // フィルター済みアイテム
    const filteredItems = useMemo(() => {
        return config.item_list.filter((item) => {
            // カテゴリーフィルター
            if (categoryFilter) {
                const itemCategory = item.category || "その他";
                if (itemCategory !== categoryFilter) return false;
            }

            // 検索クエリ
            if (searchQuery) {
                const query = searchQuery.toLowerCase();
                const nameMatch = item.name.toLowerCase().includes(query);
                const storeMatch = item.store.some(
                    (s) =>
                        s.name.toLowerCase().includes(query) ||
                        s.url?.toLowerCase().includes(query) ||
                        s.asin?.toLowerCase().includes(query) ||
                        s.search_keyword?.toLowerCase().includes(query)
                );
                if (!nameMatch && !storeMatch) return false;
            }

            return true;
        }).map((item) => ({
            item,
            originalIndex: config.item_list.findIndex((i) => i === item),
        }));
    }, [config.item_list, searchQuery, categoryFilter]);

    // アイテム追加
    const handleAddItem = useCallback(() => {
        setEditingItem({ ...DEFAULT_ITEM_DEFINITION, store: [] });
        setEditingIndex(null);
        setIsCreating(true);
    }, []);

    // アイテム編集
    const handleEditItem = useCallback((item: ItemDefinitionConfig, originalIndex: number) => {
        setEditingItem(JSON.parse(JSON.stringify(item)));
        setEditingIndex(originalIndex);
        setIsCreating(false);
    }, []);

    // アイテム削除
    const handleDeleteItem = useCallback((originalIndex: number) => {
        const item = config.item_list[originalIndex];
        if (!confirm(`アイテム「${item.name}」を削除しますか？`)) {
            return;
        }

        const newItemList = config.item_list.filter((_, i) => i !== originalIndex);
        onChange({ ...config, item_list: newItemList });
    }, [config, onChange]);

    // アイテム保存
    const handleSaveItem = useCallback((item: ItemDefinitionConfig) => {
        let newItemList: ItemDefinitionConfig[];

        if (isCreating) {
            newItemList = [...config.item_list, item];
        } else if (editingIndex !== null) {
            newItemList = config.item_list.map((i, idx) =>
                idx === editingIndex ? item : i
            );
        } else {
            return;
        }

        onChange({ ...config, item_list: newItemList });
        setEditingItem(null);
        setEditingIndex(null);
        setIsCreating(false);
    }, [config, onChange, editingIndex, isCreating]);

    // 編集キャンセル
    const handleCancel = useCallback(() => {
        setEditingItem(null);
        setEditingIndex(null);
        setIsCreating(false);
    }, []);

    // 編集フォームを表示中の場合
    if (editingItem) {
        return (
            <ItemForm
                item={editingItem}
                onSave={handleSaveItem}
                onCancel={handleCancel}
                stores={config.store_list}
                categories={config.category_list}
                isNew={isCreating}
            />
        );
    }

    return (
        <div className="space-y-4">
            {/* ヘッダー */}
            <div className="flex items-center justify-between flex-wrap gap-4">
                <h2 className="text-lg font-medium text-gray-900">
                    アイテム一覧
                    <span className="ml-2 text-sm text-gray-500">
                        ({filteredItems.length} / {config.item_list.length} 件)
                    </span>
                </h2>
                <button
                    onClick={handleAddItem}
                    className="inline-flex items-center px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                    <PlusIcon className="w-4 h-4 mr-1" />
                    アイテムを追加
                </button>
            </div>

            {/* 検索・フィルター */}
            <div className="flex gap-4 flex-wrap">
                <div className="relative flex-1 min-w-[200px]">
                    <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                    <input
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="アイテム名、ストア、URL で検索..."
                        className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                </div>
                <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                    <option value="">すべてのカテゴリー</option>
                    {availableCategories.slice(1).map((category) => (
                        <option key={category} value={category}>
                            {category}
                        </option>
                    ))}
                </select>
            </div>

            {/* アイテム一覧 */}
            {filteredItems.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                    {config.item_list.length === 0 ? (
                        <>
                            <p className="text-gray-500">アイテムが登録されていません</p>
                            <button
                                onClick={handleAddItem}
                                className="mt-4 inline-flex items-center px-4 py-2 text-sm text-blue-600 hover:text-blue-700"
                            >
                                <PlusIcon className="w-4 h-4 mr-1" />
                                最初のアイテムを追加
                            </button>
                        </>
                    ) : (
                        <p className="text-gray-500">検索条件に一致するアイテムがありません</p>
                    )}
                </div>
            ) : (
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        アイテム名
                                    </th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        カテゴリー
                                    </th>
                                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        ストア
                                    </th>
                                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                        操作
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {filteredItems.map(({ item, originalIndex }) => (
                                    <tr key={originalIndex} className="hover:bg-gray-50">
                                        <td className="px-4 py-3">
                                            <div className="text-sm font-medium text-gray-900">
                                                {item.name}
                                            </div>
                                            {item.cond && (
                                                <div className="text-xs text-gray-500">
                                                    状態: {item.cond}
                                                </div>
                                            )}
                                            {item.price && (
                                                <div className="text-xs text-gray-500">
                                                    価格: {item.price[0].toLocaleString()}
                                                    {item.price.length > 1 && ` 〜 ${item.price[1].toLocaleString()}`}
                                                    円
                                                </div>
                                            )}
                                        </td>
                                        <td className="px-4 py-3 whitespace-nowrap">
                                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                {item.category || "その他"}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3">
                                            <div className="flex flex-wrap gap-1">
                                                {item.store.map((store, storeIndex) => (
                                                    <span
                                                        key={storeIndex}
                                                        className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                                                        title={store.url || store.asin || store.search_keyword || ""}
                                                    >
                                                        {store.name}
                                                    </span>
                                                ))}
                                            </div>
                                        </td>
                                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                                            <button
                                                onClick={() => handleEditItem(item, originalIndex)}
                                                className="text-blue-600 hover:text-blue-800 p-1"
                                                title="編集"
                                            >
                                                <PencilIcon className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => handleDeleteItem(originalIndex)}
                                                className="text-red-600 hover:text-red-800 p-1 ml-2"
                                                title="削除"
                                            >
                                                <TrashIcon className="w-4 h-4" />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
