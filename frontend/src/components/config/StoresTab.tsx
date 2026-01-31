import { useState, useCallback } from "react";
import { PlusIcon, PencilIcon, TrashIcon } from "@heroicons/react/24/outline";
import type { TargetConfig, StoreDefinitionConfig } from "../../types/config";
import { CHECK_METHOD_LABELS, DEFAULT_STORE_DEFINITION } from "../../types/config";
import StoreForm from "./StoreForm";

interface StoresTabProps {
    config: TargetConfig;
    onChange: (config: TargetConfig) => void;
    checkMethods: string[];
    actionTypes: string[];
}

export default function StoresTab({ config, onChange, checkMethods, actionTypes }: StoresTabProps) {
    const [editingStore, setEditingStore] = useState<StoreDefinitionConfig | null>(null);
    const [editingIndex, setEditingIndex] = useState<number | null>(null);
    const [isCreating, setIsCreating] = useState(false);

    // ストア追加
    const handleAddStore = useCallback(() => {
        setEditingStore({ ...DEFAULT_STORE_DEFINITION });
        setEditingIndex(null);
        setIsCreating(true);
    }, []);

    // ストア編集
    const handleEditStore = useCallback((store: StoreDefinitionConfig, index: number) => {
        setEditingStore({ ...store });
        setEditingIndex(index);
        setIsCreating(false);
    }, []);

    // ストア削除
    const handleDeleteStore = useCallback((index: number) => {
        const storeName = config.store_list[index].name;
        // このストアを使用しているアイテムがあるか確認
        const usedByItems = config.item_list.filter((item) =>
            item.store.some((s) => s.name === storeName)
        );

        if (usedByItems.length > 0) {
            alert(
                `このストアは ${usedByItems.length} 個のアイテムで使用されています。\n` +
                `先にアイテムからこのストアを削除してください。`
            );
            return;
        }

        if (!confirm(`ストア「${storeName}」を削除しますか？`)) {
            return;
        }

        const newStoreList = config.store_list.filter((_, i) => i !== index);
        onChange({ ...config, store_list: newStoreList });
    }, [config, onChange]);

    // ストア保存
    const handleSaveStore = useCallback((store: StoreDefinitionConfig) => {
        let newStoreList: StoreDefinitionConfig[];

        if (isCreating) {
            // 新規追加
            newStoreList = [...config.store_list, store];
        } else if (editingIndex !== null) {
            // 更新
            newStoreList = config.store_list.map((s, i) =>
                i === editingIndex ? store : s
            );
        } else {
            return;
        }

        onChange({ ...config, store_list: newStoreList });
        setEditingStore(null);
        setEditingIndex(null);
        setIsCreating(false);
    }, [config, onChange, editingIndex, isCreating]);

    // 編集キャンセル
    const handleCancel = useCallback(() => {
        setEditingStore(null);
        setEditingIndex(null);
        setIsCreating(false);
    }, []);

    // 編集フォームを表示中の場合
    if (editingStore) {
        return (
            <StoreForm
                store={editingStore}
                onSave={handleSaveStore}
                onCancel={handleCancel}
                checkMethods={checkMethods}
                actionTypes={actionTypes}
                isNew={isCreating}
                existingNames={config.store_list
                    .filter((_, i) => i !== editingIndex)
                    .map((s) => s.name)}
            />
        );
    }

    return (
        <div className="space-y-4">
            {/* ヘッダー */}
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-medium text-gray-900">
                    ストア一覧
                    <span className="ml-2 text-sm text-gray-500">
                        ({config.store_list.length} 件)
                    </span>
                </h2>
                <button
                    onClick={handleAddStore}
                    className="inline-flex items-center px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                    <PlusIcon className="w-4 h-4 mr-1" />
                    ストアを追加
                </button>
            </div>

            {/* ストア一覧 */}
            {config.store_list.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                    <p className="text-gray-500">ストアが登録されていません</p>
                    <button
                        onClick={handleAddStore}
                        className="mt-4 inline-flex items-center px-4 py-2 text-sm text-blue-600 hover:text-blue-700"
                    >
                        <PlusIcon className="w-4 h-4 mr-1" />
                        最初のストアを追加
                    </button>
                </div>
            ) : (
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    ストア名
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    チェック方法
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    通貨
                                </th>
                                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    ポイント還元率
                                </th>
                                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    操作
                                </th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {config.store_list.map((store, index) => (
                                <tr key={index} className="hover:bg-gray-50">
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        <div className="flex items-center">
                                            {store.color && (
                                                <span
                                                    className="w-3 h-3 rounded-full mr-2"
                                                    style={{ backgroundColor: store.color }}
                                                />
                                            )}
                                            <span className="text-sm font-medium text-gray-900">
                                                {store.name}
                                            </span>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                                        {CHECK_METHOD_LABELS[store.check_method as keyof typeof CHECK_METHOD_LABELS] || store.check_method}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                                        {store.price_unit}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500">
                                        {store.point_rate > 0 ? `${store.point_rate}%` : "-"}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap text-right text-sm">
                                        <button
                                            onClick={() => handleEditStore(store, index)}
                                            className="text-blue-600 hover:text-blue-800 p-1"
                                            title="編集"
                                        >
                                            <PencilIcon className="w-4 h-4" />
                                        </button>
                                        <button
                                            onClick={() => handleDeleteStore(index)}
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
            )}
        </div>
    );
}
