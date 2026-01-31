import { useState, useCallback, useMemo } from "react";
import { PlusIcon, TrashIcon, Bars3Icon } from "@heroicons/react/24/outline";
import type { TargetConfig } from "../../types/config";

interface CategoriesTabProps {
    config: TargetConfig;
    onChange: (config: TargetConfig) => void;
}

export default function CategoriesTab({ config, onChange }: CategoriesTabProps) {
    const [newCategory, setNewCategory] = useState("");
    const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
    const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

    // アイテムで使用されているカテゴリーを収集
    const usedCategories = useMemo(() => {
        const categories = new Set<string>();
        config.item_list.forEach((item) => {
            if (item.category) {
                categories.add(item.category);
            }
        });
        return categories;
    }, [config.item_list]);

    // カテゴリー追加
    const handleAddCategory = useCallback(() => {
        const trimmed = newCategory.trim();
        if (!trimmed) return;

        if (config.category_list.includes(trimmed)) {
            alert("このカテゴリーは既に存在します");
            return;
        }

        onChange({
            ...config,
            category_list: [...config.category_list, trimmed],
        });
        setNewCategory("");
    }, [config, onChange, newCategory]);

    // カテゴリー削除
    const handleDeleteCategory = useCallback((index: number) => {
        const category = config.category_list[index];
        const usageCount = config.item_list.filter((item) => item.category === category).length;

        if (usageCount > 0) {
            alert(`このカテゴリーは ${usageCount} 個のアイテムで使用されています。`);
            return;
        }

        if (!confirm(`カテゴリー「${category}」を削除しますか？`)) {
            return;
        }

        onChange({
            ...config,
            category_list: config.category_list.filter((_, i) => i !== index),
        });
    }, [config, onChange]);

    // ドラッグ開始
    const handleDragStart = useCallback((index: number) => {
        setDraggedIndex(index);
    }, []);

    // ドラッグオーバー
    const handleDragOver = useCallback((e: React.DragEvent, index: number) => {
        e.preventDefault();
        setDragOverIndex(index);
    }, []);

    // ドラッグ終了
    const handleDragEnd = useCallback(() => {
        if (draggedIndex !== null && dragOverIndex !== null && draggedIndex !== dragOverIndex) {
            const newList = [...config.category_list];
            const [removed] = newList.splice(draggedIndex, 1);
            newList.splice(dragOverIndex, 0, removed);

            onChange({
                ...config,
                category_list: newList,
            });
        }

        setDraggedIndex(null);
        setDragOverIndex(null);
    }, [config, onChange, draggedIndex, dragOverIndex]);

    // Enter キーで追加
    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            e.preventDefault();
            handleAddCategory();
        }
    }, [handleAddCategory]);

    return (
        <div className="space-y-4">
            {/* ヘッダー */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-medium text-gray-900">
                        カテゴリー表示順
                        <span className="ml-2 text-sm text-gray-500">
                            ({config.category_list.length} 件)
                        </span>
                    </h2>
                    <p className="mt-1 text-sm text-gray-500">
                        ドラッグ&ドロップで表示順を変更できます。
                        「その他」はリストにない場合は末尾に表示されます。
                    </p>
                </div>
            </div>

            {/* カテゴリー追加 */}
            <div className="flex gap-2">
                <input
                    type="text"
                    value={newCategory}
                    onChange={(e) => setNewCategory(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="新しいカテゴリー名"
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <button
                    onClick={handleAddCategory}
                    disabled={!newCategory.trim()}
                    className="inline-flex items-center px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    <PlusIcon className="w-4 h-4 mr-1" />
                    追加
                </button>
            </div>

            {/* カテゴリー一覧 */}
            {config.category_list.length === 0 ? (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                    <p className="text-gray-500 mb-2">カテゴリーが登録されていません</p>
                    <p className="text-sm text-gray-400">
                        カテゴリーを登録しない場合、アイテムはアルファベット順で表示されます。
                    </p>
                </div>
            ) : (
                <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
                    <ul className="divide-y divide-gray-200">
                        {config.category_list.map((category, index) => {
                            const isUsed = usedCategories.has(category);
                            const isDragging = draggedIndex === index;
                            const isDragOver = dragOverIndex === index && draggedIndex !== index;

                            return (
                                <li
                                    key={index}
                                    draggable
                                    onDragStart={() => handleDragStart(index)}
                                    onDragOver={(e) => handleDragOver(e, index)}
                                    onDragEnd={handleDragEnd}
                                    className={`flex items-center px-4 py-3 transition-colors cursor-move ${
                                        isDragging ? "opacity-50 bg-blue-50" : ""
                                    } ${isDragOver ? "bg-blue-100 border-t-2 border-blue-500" : ""}`}
                                >
                                    <Bars3Icon className="w-5 h-5 text-gray-400 mr-3 flex-shrink-0" />
                                    <span className="flex-1 text-sm text-gray-900">{category}</span>
                                    {isUsed && (
                                        <span className="text-xs text-gray-400 mr-3">使用中</span>
                                    )}
                                    <button
                                        onClick={() => handleDeleteCategory(index)}
                                        className="p-1 text-red-600 hover:text-red-800 transition-colors"
                                        title="削除"
                                    >
                                        <TrashIcon className="w-4 h-4" />
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </div>
            )}

            {/* アイテムで使用されているが未登録のカテゴリー */}
            {(() => {
                const unregisteredCategories = [...usedCategories].filter(
                    (cat) => !config.category_list.includes(cat)
                );
                if (unregisteredCategories.length === 0) return null;

                return (
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                        <h3 className="text-sm font-medium text-yellow-800 mb-2">
                            未登録のカテゴリー
                        </h3>
                        <p className="text-sm text-yellow-700 mb-3">
                            以下のカテゴリーはアイテムで使用されていますが、表示順が設定されていません。
                        </p>
                        <div className="flex flex-wrap gap-2">
                            {unregisteredCategories.map((category) => (
                                <button
                                    key={category}
                                    onClick={() => {
                                        onChange({
                                            ...config,
                                            category_list: [...config.category_list, category],
                                        });
                                    }}
                                    className="inline-flex items-center px-3 py-1 text-sm bg-yellow-100 text-yellow-800 rounded-full hover:bg-yellow-200 transition-colors"
                                >
                                    <PlusIcon className="w-3 h-3 mr-1" />
                                    {category}
                                </button>
                            ))}
                        </div>
                    </div>
                );
            })()}
        </div>
    );
}
