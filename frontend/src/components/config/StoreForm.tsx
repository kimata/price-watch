import { useState, useCallback } from "react";
import { PlusIcon, TrashIcon } from "@heroicons/react/24/outline";
import type { StoreDefinitionConfig, ActionStep, CheckMethod, ActionType } from "../../types/config";
import { CHECK_METHOD_LABELS, ACTION_TYPE_LABELS } from "../../types/config";
import XPathInput from "./XPathInput";

interface StoreFormProps {
    store: StoreDefinitionConfig;
    onSave: (store: StoreDefinitionConfig) => void;
    onCancel: () => void;
    checkMethods: string[];
    actionTypes: string[];
    isNew: boolean;
    existingNames: string[];
}

export default function StoreForm({
    store: initialStore,
    onSave,
    onCancel,
    checkMethods,
    actionTypes,
    isNew,
    existingNames,
}: StoreFormProps) {
    const [store, setStore] = useState<StoreDefinitionConfig>(initialStore);
    const [errors, setErrors] = useState<Record<string, string>>({});

    // スクレイピングストアかどうか
    const isScrape = store.check_method === "scrape";

    // バリデーション
    const validate = useCallback(() => {
        const newErrors: Record<string, string> = {};

        if (!store.name.trim()) {
            newErrors.name = "ストア名は必須です";
        } else if (existingNames.includes(store.name.trim())) {
            newErrors.name = "このストア名は既に使用されています";
        }

        if (store.point_rate < 0 || store.point_rate > 100) {
            newErrors.point_rate = "ポイント還元率は 0〜100 の範囲で入力してください";
        }

        if (store.color && !/^#[0-9A-Fa-f]{6}$/.test(store.color)) {
            newErrors.color = "色は #RRGGBB 形式で入力してください";
        }

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    }, [store, existingNames]);

    // 保存
    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        if (validate()) {
            // 空の値を null に変換
            const cleanedStore: StoreDefinitionConfig = {
                ...store,
                name: store.name.trim(),
                price_xpath: store.price_xpath?.trim() || null,
                thumb_img_xpath: store.thumb_img_xpath?.trim() || null,
                unavailable_xpath: store.unavailable_xpath?.trim() || null,
                color: store.color?.trim() || null,
                affiliate_id: store.affiliate_id?.trim() || null,
            };
            onSave(cleanedStore);
        }
    }, [store, validate, onSave]);

    // フィールド更新
    const updateField = useCallback(<K extends keyof StoreDefinitionConfig>(
        field: K,
        value: StoreDefinitionConfig[K]
    ) => {
        setStore((prev) => ({ ...prev, [field]: value }));
    }, []);

    // アクション追加
    const addAction = useCallback(() => {
        const newAction: ActionStep = { type: "click" as ActionType, xpath: "", value: null };
        setStore((prev) => ({ ...prev, action: [...prev.action, newAction] }));
    }, []);

    // アクション更新
    const updateAction = useCallback((index: number, action: ActionStep) => {
        setStore((prev) => ({
            ...prev,
            action: prev.action.map((a, i) => (i === index ? action : a)),
        }));
    }, []);

    // アクション削除
    const removeAction = useCallback((index: number) => {
        setStore((prev) => ({
            ...prev,
            action: prev.action.filter((_, i) => i !== index),
        }));
    }, []);

    return (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-6">
                {isNew ? "ストアを追加" : "ストアを編集"}
            </h3>

            <div className="space-y-6">
                {/* 基本情報 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* ストア名 */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            ストア名 <span className="text-red-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={store.name}
                            onChange={(e) => updateField("name", e.target.value)}
                            className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                                errors.name ? "border-red-300" : "border-gray-300"
                            }`}
                            placeholder="例: ヨドバシ"
                        />
                        {errors.name && (
                            <p className="mt-1 text-sm text-red-600">{errors.name}</p>
                        )}
                    </div>

                    {/* チェック方法 */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            チェック方法
                        </label>
                        <select
                            value={store.check_method}
                            onChange={(e) => updateField("check_method", e.target.value as CheckMethod)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            {checkMethods.map((method) => (
                                <option key={method} value={method}>
                                    {CHECK_METHOD_LABELS[method as keyof typeof CHECK_METHOD_LABELS] || method}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* 通貨単位 */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            通貨単位
                        </label>
                        <input
                            type="text"
                            value={store.price_unit}
                            onChange={(e) => updateField("price_unit", e.target.value)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            placeholder="円"
                        />
                    </div>

                    {/* ポイント還元率 */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            ポイント還元率 (%)
                        </label>
                        <input
                            type="number"
                            value={store.point_rate}
                            onChange={(e) => updateField("point_rate", parseFloat(e.target.value) || 0)}
                            min="0"
                            max="100"
                            step="0.1"
                            className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                                errors.point_rate ? "border-red-300" : "border-gray-300"
                            }`}
                        />
                        {errors.point_rate && (
                            <p className="mt-1 text-sm text-red-600">{errors.point_rate}</p>
                        )}
                    </div>

                    {/* 色 */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            色
                        </label>
                        <div className="flex gap-2">
                            <input
                                type="color"
                                value={store.color || "#3b82f6"}
                                onChange={(e) => updateField("color", e.target.value)}
                                className="w-12 h-10 cursor-pointer"
                            />
                            <input
                                type="text"
                                value={store.color || ""}
                                onChange={(e) => updateField("color", e.target.value || null)}
                                className={`flex-1 px-3 py-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                                    errors.color ? "border-red-300" : "border-gray-300"
                                }`}
                                placeholder="#3b82f6"
                            />
                        </div>
                        {errors.color && (
                            <p className="mt-1 text-sm text-red-600">{errors.color}</p>
                        )}
                    </div>

                    {/* アフィリエイトID */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            アフィリエイトID
                        </label>
                        <input
                            type="text"
                            value={store.affiliate_id || ""}
                            onChange={(e) => updateField("affiliate_id", e.target.value || null)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            placeholder="例: my-affiliate-tag"
                        />
                        <p className="mt-1 text-xs text-gray-500">
                            URLに付与するアフィリエイトタグ（Amazon: ?tag=..., フリマ: ?afid=...）
                        </p>
                    </div>
                </div>

                {/* スクレイピング設定（スクレイピングストアのみ） */}
                {isScrape && (
                    <div className="border-t border-gray-200 pt-6">
                        <h4 className="text-sm font-medium text-gray-900 mb-4">
                            スクレイピング設定
                        </h4>
                        <div className="space-y-4">
                            <XPathInput
                                label="価格の XPath"
                                value={store.price_xpath || ""}
                                onChange={(value) => updateField("price_xpath", value || null)}
                                placeholder='例: //span[@class="price"]/text()'
                            />
                            <XPathInput
                                label="サムネイル画像の XPath"
                                value={store.thumb_img_xpath || ""}
                                onChange={(value) => updateField("thumb_img_xpath", value || null)}
                                placeholder='例: //img[@id="mainImage"]/@src'
                            />
                            <XPathInput
                                label="在庫なし判定の XPath"
                                value={store.unavailable_xpath || ""}
                                onChange={(value) => updateField("unavailable_xpath", value || null)}
                                placeholder='例: //div[text()="在庫なし"]'
                            />
                        </div>
                    </div>
                )}

                {/* アクション設定（スクレイピングストアのみ） */}
                {isScrape && (
                    <div className="border-t border-gray-200 pt-6">
                        <div className="flex items-center justify-between mb-4">
                            <h4 className="text-sm font-medium text-gray-900">
                                アクション（ページ操作）
                            </h4>
                            <button
                                type="button"
                                onClick={addAction}
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-700"
                            >
                                <PlusIcon className="w-4 h-4 mr-1" />
                                アクションを追加
                            </button>
                        </div>

                        {store.action.length === 0 ? (
                            <p className="text-sm text-gray-500">
                                アクションはありません
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {store.action.map((action, index) => (
                                    <div key={index} className="flex items-start gap-2 p-3 bg-gray-50 rounded-md">
                                        <div className="flex-1 grid grid-cols-1 md:grid-cols-3 gap-2">
                                            <select
                                                value={action.type}
                                                onChange={(e) =>
                                                    updateAction(index, {
                                                        ...action,
                                                        type: e.target.value as ActionType,
                                                    })
                                                }
                                                className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                                            >
                                                {actionTypes.map((type) => (
                                                    <option key={type} value={type}>
                                                        {ACTION_TYPE_LABELS[type as ActionType] || type}
                                                    </option>
                                                ))}
                                            </select>
                                            <input
                                                type="text"
                                                value={action.xpath || ""}
                                                onChange={(e) =>
                                                    updateAction(index, {
                                                        ...action,
                                                        xpath: e.target.value || null,
                                                    })
                                                }
                                                placeholder="XPath"
                                                className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                                            />
                                            {action.type === "input" && (
                                                <input
                                                    type="text"
                                                    value={action.value || ""}
                                                    onChange={(e) =>
                                                        updateAction(index, {
                                                            ...action,
                                                            value: e.target.value || null,
                                                        })
                                                    }
                                                    placeholder="入力値"
                                                    className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                />
                                            )}
                                        </div>
                                        <button
                                            type="button"
                                            onClick={() => removeAction(index)}
                                            className="p-2 text-red-600 hover:text-red-800"
                                        >
                                            <TrashIcon className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* ボタン */}
            <div className="flex justify-end gap-3 mt-6 pt-6 border-t border-gray-200">
                <button
                    type="button"
                    onClick={onCancel}
                    className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
                >
                    キャンセル
                </button>
                <button
                    type="submit"
                    className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                    {isNew ? "追加" : "保存"}
                </button>
            </div>
        </form>
    );
}
