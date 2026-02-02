import { useState, useCallback, useMemo, useEffect } from "react";
import { PlusIcon, TrashIcon, PlayIcon, MagnifyingGlassIcon } from "@heroicons/react/24/outline";
import type {
    ItemDefinitionConfig,
    StoreDefinitionConfig,
    StoreEntryConfig,
    CheckMethod,
} from "../../types/config";
import { DEFAULT_STORE_ENTRY, CHECK_METHOD_LABELS } from "../../types/config";
import XPathInput from "./XPathInput";
import CheckItemModal from "./CheckItemModal";
import AmazonSearchModal from "./AmazonSearchModal";
import { checkAmazonSearchAvailable } from "../../services/configService";

interface ItemFormProps {
    item: ItemDefinitionConfig;
    onSave: (item: ItemDefinitionConfig) => void;
    onCancel: () => void;
    stores: StoreDefinitionConfig[];
    categories: string[];
    isNew: boolean;
    /** target.yaml に保存済みのアイテムかどうか（動作確認ボタンの有効化に使用） */
    isSaved: boolean;
}

export default function ItemForm({
    item: initialItem,
    onSave,
    onCancel,
    stores,
    categories,
    isNew,
    isSaved,
}: ItemFormProps) {
    const [item, setItem] = useState<ItemDefinitionConfig>(initialItem);
    const [errors, setErrors] = useState<Record<string, string>>({});
    const [checkModalStore, setCheckModalStore] = useState<{
        storeName: string;
        storeConfig: StoreDefinitionConfig;
    } | null>(null);
    const [amazonSearchModal, setAmazonSearchModal] = useState<{
        storeIndex: number;
        defaultKeyword: string;
    } | null>(null);
    const [isAmazonSearchAvailable, setIsAmazonSearchAvailable] = useState(false);

    // Amazon 検索 API の利用可能状態を確認
    useEffect(() => {
        checkAmazonSearchAvailable()
            .then(setIsAmazonSearchAvailable)
            .catch(() => setIsAmazonSearchAvailable(false));
    }, []);

    // ストア定義のマップ（名前 → 定義）
    const storeMap = useMemo(() => {
        return new Map(stores.map((s) => [s.name, s]));
    }, [stores]);

    // バリデーション
    const validate = useCallback(() => {
        const newErrors: Record<string, string> = {};

        if (!item.name.trim()) {
            newErrors.name = "アイテム名は必須です";
        }

        if (item.store.length === 0) {
            newErrors.store = "少なくとも1つのストアを追加してください";
        }

        // 各ストアエントリのバリデーション
        item.store.forEach((storeEntry, index) => {
            const storeDef = storeMap.get(storeEntry.name);
            if (!storeDef) {
                newErrors[`store.${index}.name`] = "存在しないストアです";
                return;
            }

            // スクレイピングストアの場合は URL または ASIN が必要
            if (storeDef.check_method === "scrape") {
                if (!storeEntry.url && !storeEntry.asin) {
                    newErrors[`store.${index}`] = "URL または ASIN が必要です";
                }
            }
        });

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    }, [item, storeMap]);

    // 保存
    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        if (validate()) {
            // 空の値をクリーンアップ
            const cleanedItem: ItemDefinitionConfig = {
                ...item,
                name: item.name.trim(),
                category: item.category?.trim() || null,
                price: item.price && item.price.length > 0 ? item.price : null,
                cond: item.cond?.trim() || null,
                store: item.store.map((s) => ({
                    ...s,
                    url: s.url?.trim() || null,
                    asin: s.asin?.trim() || null,
                    search_keyword: s.search_keyword?.trim() || null,
                    exclude_keyword: s.exclude_keyword?.trim() || null,
                    jan_code: s.jan_code?.trim() || null,
                    cond: s.cond?.trim() || null,
                    price_xpath: s.price_xpath?.trim() || null,
                    thumb_img_xpath: s.thumb_img_xpath?.trim() || null,
                    unavailable_xpath: s.unavailable_xpath?.trim() || null,
                    price_unit: s.price_unit?.trim() || null,
                    price: s.price && s.price.length > 0 ? s.price : null,
                })),
            };
            onSave(cleanedItem);
        }
    }, [item, validate, onSave]);

    // フィールド更新
    const updateField = useCallback(<K extends keyof ItemDefinitionConfig>(
        field: K,
        value: ItemDefinitionConfig[K]
    ) => {
        setItem((prev) => ({ ...prev, [field]: value }));
    }, []);

    // ストアエントリ追加
    const addStoreEntry = useCallback(() => {
        // 未使用のストアを探す
        const usedStoreNames = new Set(item.store.map((s) => s.name));
        const unusedStore = stores.find((s) => !usedStoreNames.has(s.name));

        const newEntry: StoreEntryConfig = {
            ...DEFAULT_STORE_ENTRY,
            name: unusedStore?.name || "",
        };
        setItem((prev) => ({ ...prev, store: [...prev.store, newEntry] }));
    }, [item.store, stores]);

    // ストアエントリ更新
    const updateStoreEntry = useCallback((index: number, entry: StoreEntryConfig) => {
        setItem((prev) => ({
            ...prev,
            store: prev.store.map((s, i) => (i === index ? entry : s)),
        }));
    }, []);

    // ストアエントリ削除
    const removeStoreEntry = useCallback((index: number) => {
        setItem((prev) => ({
            ...prev,
            store: prev.store.filter((_, i) => i !== index),
        }));
    }, []);

    // フリマ一括追加（メルカリ、ラクマ、PayPayフリマ）
    const FLEA_MARKET_METHODS = [
        "my_lib.store.mercari.search",
        "my_lib.store.rakuma.search",
        "my_lib.store.paypay.search",
    ];

    const fleaMarketStores = useMemo(() => {
        return stores.filter((s) => FLEA_MARKET_METHODS.includes(s.check_method));
    }, [stores]);

    const addFleaMarketStores = useCallback(() => {
        const usedStoreNames = new Set(item.store.map((s) => s.name));
        const newEntries: StoreEntryConfig[] = fleaMarketStores
            .filter((s) => !usedStoreNames.has(s.name))
            .map((s) => ({
                ...DEFAULT_STORE_ENTRY,
                name: s.name,
            }));

        if (newEntries.length > 0) {
            setItem((prev) => ({ ...prev, store: [...prev.store, ...newEntries] }));
        }
    }, [item.store, fleaMarketStores]);

    // 価格範囲の更新
    const updatePriceRange = useCallback((min: string, max: string) => {
        const minVal = parseInt(min, 10);
        const maxVal = parseInt(max, 10);

        if (isNaN(minVal) && isNaN(maxVal)) {
            updateField("price", null);
        } else if (isNaN(maxVal) || maxVal === 0) {
            updateField("price", [minVal || 0]);
        } else {
            updateField("price", [minVal || 0, maxVal]);
        }
    }, [updateField]);

    return (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg border border-gray-200 p-6">
            <h3 className="text-lg font-medium text-gray-900 mb-6">
                {isNew ? "アイテムを追加" : "アイテムを編集"}
            </h3>

            <div className="space-y-6">
                {/* 基本情報 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* アイテム名 */}
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            アイテム名 <span className="text-red-500">*</span>
                        </label>
                        <input
                            type="text"
                            value={item.name}
                            onChange={(e) => updateField("name", e.target.value)}
                            className={`w-full px-3 py-2 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                                errors.name ? "border-red-300" : "border-gray-300"
                            }`}
                            placeholder="例: Apple Watch Series 9"
                        />
                        {errors.name && (
                            <p className="mt-1 text-sm text-red-600">{errors.name}</p>
                        )}
                    </div>

                    {/* カテゴリー */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            カテゴリー
                        </label>
                        <select
                            value={item.category || ""}
                            onChange={(e) => updateField("category", e.target.value || null)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value="">その他（未設定）</option>
                            {categories.map((cat) => (
                                <option key={cat} value={cat}>
                                    {cat}
                                </option>
                            ))}
                        </select>
                    </div>

                    {/* 商品状態（アイテムレベル） */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            商品状態（共通）
                        </label>
                        <input
                            type="text"
                            value={item.cond || ""}
                            onChange={(e) => updateField("cond", e.target.value || null)}
                            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            placeholder="例: NEW|LIKE_NEW"
                        />
                        <p className="mt-1 text-xs text-gray-500">
                            フリマ検索の場合の商品状態フィルター
                        </p>
                    </div>

                    {/* 価格範囲（アイテムレベル） */}
                    <div className="md:col-span-2">
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                            価格範囲（共通）
                        </label>
                        <div className="flex items-center gap-2">
                            <input
                                type="number"
                                value={item.price?.[0] || ""}
                                onChange={(e) =>
                                    updatePriceRange(e.target.value, String(item.price?.[1] || ""))
                                }
                                min="0"
                                className="w-32 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                placeholder="下限"
                            />
                            <span className="text-gray-500">〜</span>
                            <input
                                type="number"
                                value={item.price?.[1] || ""}
                                onChange={(e) =>
                                    updatePriceRange(String(item.price?.[0] || ""), e.target.value)
                                }
                                min="0"
                                className="w-32 px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                placeholder="上限"
                            />
                            <span className="text-gray-500">円</span>
                        </div>
                        <p className="mt-1 text-xs text-gray-500">
                            検索系ストアの価格フィルター（ストアエントリで上書き可能）
                        </p>
                    </div>
                </div>

                {/* ストアエントリ */}
                <div className="border-t border-gray-200 pt-6">
                    <div className="flex items-center justify-between mb-4">
                        <h4 className="text-sm font-medium text-gray-900">
                            ストア <span className="text-red-500">*</span>
                        </h4>
                        <div className="flex items-center gap-3">
                            {fleaMarketStores.length > 0 && (
                                <button
                                    type="button"
                                    onClick={addFleaMarketStores}
                                    className="inline-flex items-center text-sm text-green-600 hover:text-green-700"
                                >
                                    <PlusIcon className="w-4 h-4 mr-1" />
                                    フリマ一括追加
                                </button>
                            )}
                            <button
                                type="button"
                                onClick={addStoreEntry}
                                disabled={stores.length === 0}
                                className="inline-flex items-center text-sm text-blue-600 hover:text-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <PlusIcon className="w-4 h-4 mr-1" />
                                ストアを追加
                            </button>
                        </div>
                    </div>

                    {errors.store && (
                        <p className="mb-4 text-sm text-red-600">{errors.store}</p>
                    )}

                    {item.store.length === 0 ? (
                        <p className="text-sm text-gray-500">
                            ストアを追加してください
                        </p>
                    ) : (
                        <div className="space-y-4">
                            {item.store.map((storeEntry, index) => {
                                const storeDef = storeMap.get(storeEntry.name);
                                const checkMethod = storeDef?.check_method || "scrape";
                                const isScrape = checkMethod === "scrape" || checkMethod === "my_lib.store.yodobashi.scrape";
                                const isSearch = [
                                    "my_lib.store.mercari.search",
                                    "my_lib.store.rakuma.search",
                                    "my_lib.store.paypay.search",
                                    "my_lib.store.yahoo.api",
                                    "my_lib.store.rakuten.api",
                                ].includes(checkMethod);

                                return (
                                    <div key={index} className="p-4 bg-gray-50 rounded-lg">
                                        <div className="flex items-start gap-2">
                                            <div className="flex-1 space-y-3">
                                                {/* ストア選択 */}
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                    <div>
                                                        <label className="block text-xs font-medium text-gray-700 mb-1">
                                                            ストア
                                                        </label>
                                                        <select
                                                            value={storeEntry.name}
                                                            onChange={(e) =>
                                                                updateStoreEntry(index, {
                                                                    ...storeEntry,
                                                                    name: e.target.value,
                                                                })
                                                            }
                                                            className={`w-full px-3 py-2 border rounded-md text-sm ${
                                                                errors[`store.${index}.name`]
                                                                    ? "border-red-300"
                                                                    : "border-gray-300"
                                                            }`}
                                                        >
                                                            <option value="">選択してください</option>
                                                            {stores.map((store) => (
                                                                <option key={store.name} value={store.name}>
                                                                    {store.name} ({CHECK_METHOD_LABELS[store.check_method as CheckMethod] || store.check_method})
                                                                </option>
                                                            ))}
                                                        </select>
                                                    </div>

                                                    {/* スクレイピング: URL */}
                                                    {isScrape && (
                                                        <div>
                                                            <label className="block text-xs font-medium text-gray-700 mb-1">
                                                                URL
                                                            </label>
                                                            <input
                                                                type="text"
                                                                value={storeEntry.url || ""}
                                                                onChange={(e) =>
                                                                    updateStoreEntry(index, {
                                                                        ...storeEntry,
                                                                        url: e.target.value || null,
                                                                    })
                                                                }
                                                                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                                placeholder="https://..."
                                                            />
                                                        </div>
                                                    )}

                                                    {/* Amazon: ASIN */}
                                                    {checkMethod === "my_lib.store.amazon.api" && (
                                                        <div>
                                                            <label className="block text-xs font-medium text-gray-700 mb-1">
                                                                ASIN
                                                            </label>
                                                            <div className="flex gap-2">
                                                                <input
                                                                    type="text"
                                                                    value={storeEntry.asin || ""}
                                                                    onChange={(e) =>
                                                                        updateStoreEntry(index, {
                                                                            ...storeEntry,
                                                                            asin: e.target.value || null,
                                                                        })
                                                                    }
                                                                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                                    placeholder="B0XXXXXXXX"
                                                                />
                                                                {isAmazonSearchAvailable && (
                                                                    <button
                                                                        type="button"
                                                                        onClick={() =>
                                                                            setAmazonSearchModal({
                                                                                storeIndex: index,
                                                                                defaultKeyword: storeEntry.search_keyword || item.name,
                                                                            })
                                                                        }
                                                                        className="inline-flex items-center px-3 py-2 text-sm bg-orange-500 text-white rounded-md hover:bg-orange-600 transition-colors"
                                                                        title="Amazon で検索して ASIN を選択"
                                                                    >
                                                                        <MagnifyingGlassIcon className="w-4 h-4 mr-1" />
                                                                        検索
                                                                    </button>
                                                                )}
                                                            </div>
                                                        </div>
                                                    )}

                                                    {/* 検索系: キーワード */}
                                                    {isSearch && (
                                                        <>
                                                            <div>
                                                                <label className="block text-xs font-medium text-gray-700 mb-1">
                                                                    検索キーワード
                                                                </label>
                                                                <input
                                                                    type="text"
                                                                    value={storeEntry.search_keyword || ""}
                                                                    onChange={(e) =>
                                                                        updateStoreEntry(index, {
                                                                            ...storeEntry,
                                                                            search_keyword: e.target.value || null,
                                                                        })
                                                                    }
                                                                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                                    placeholder="空欄時はアイテム名で検索"
                                                                />
                                                            </div>
                                                            {checkMethod !== "my_lib.store.yahoo.api" && (
                                                                <div>
                                                                    <label className="block text-xs font-medium text-gray-700 mb-1">
                                                                        除外キーワード
                                                                    </label>
                                                                    <input
                                                                        type="text"
                                                                        value={storeEntry.exclude_keyword || ""}
                                                                        onChange={(e) =>
                                                                            updateStoreEntry(index, {
                                                                                ...storeEntry,
                                                                                exclude_keyword: e.target.value || null,
                                                                            })
                                                                        }
                                                                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                                        placeholder="ジャンク"
                                                                    />
                                                                </div>
                                                            )}
                                                            {checkMethod === "my_lib.store.yahoo.api" && (
                                                                <div>
                                                                    <label className="block text-xs font-medium text-gray-700 mb-1">
                                                                        JANコード
                                                                    </label>
                                                                    <input
                                                                        type="text"
                                                                        value={storeEntry.jan_code || ""}
                                                                        onChange={(e) =>
                                                                            updateStoreEntry(index, {
                                                                                ...storeEntry,
                                                                                jan_code: e.target.value || null,
                                                                            })
                                                                        }
                                                                        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                                                                        placeholder="4901234567890"
                                                                    />
                                                                </div>
                                                            )}
                                                        </>
                                                    )}
                                                </div>

                                                {errors[`store.${index}`] && (
                                                    <p className="text-sm text-red-600">{errors[`store.${index}`]}</p>
                                                )}

                                                {/* スクレイピング: XPath（オプション） */}
                                                {isScrape && (
                                                    <details className="text-sm">
                                                        <summary className="cursor-pointer text-gray-600 hover:text-gray-800">
                                                            詳細設定（XPath 等）
                                                        </summary>
                                                        <div className="mt-3 space-y-3">
                                                            <XPathInput
                                                                label="価格の XPath（ストア定義を上書き）"
                                                                value={storeEntry.price_xpath || ""}
                                                                onChange={(v) =>
                                                                    updateStoreEntry(index, {
                                                                        ...storeEntry,
                                                                        price_xpath: v || null,
                                                                    })
                                                                }
                                                            />
                                                            <XPathInput
                                                                label="サムネイル画像の XPath"
                                                                value={storeEntry.thumb_img_xpath || ""}
                                                                onChange={(v) =>
                                                                    updateStoreEntry(index, {
                                                                        ...storeEntry,
                                                                        thumb_img_xpath: v || null,
                                                                    })
                                                                }
                                                            />
                                                            <XPathInput
                                                                label="在庫なし判定の XPath"
                                                                value={storeEntry.unavailable_xpath || ""}
                                                                onChange={(v) =>
                                                                    updateStoreEntry(index, {
                                                                        ...storeEntry,
                                                                        unavailable_xpath: v || null,
                                                                    })
                                                                }
                                                            />
                                                        </div>
                                                    </details>
                                                )}
                                            </div>
                                            <div className="flex flex-col gap-1">
                                                {storeDef && (
                                                    <button
                                                        type="button"
                                                        onClick={() =>
                                                            isSaved
                                                                ? setCheckModalStore({
                                                                      storeName: storeEntry.name,
                                                                      storeConfig: storeDef,
                                                                  })
                                                                : alert(
                                                                      "動作確認を行うには、先にアイテムを保存してください。\n\n" +
                                                                          "セキュリティ上の理由により、保存済みのアイテムのみ動作確認できます。"
                                                                  )
                                                        }
                                                        className={`p-2 ${
                                                            isSaved
                                                                ? "text-blue-600 hover:text-blue-800"
                                                                : "text-gray-400 cursor-not-allowed"
                                                        }`}
                                                        title={
                                                            isSaved
                                                                ? "動作確認"
                                                                : "動作確認するには先にアイテムを保存してください"
                                                        }
                                                    >
                                                        <PlayIcon className="w-4 h-4" />
                                                    </button>
                                                )}
                                                <button
                                                    type="button"
                                                    onClick={() => removeStoreEntry(index)}
                                                    className="p-2 text-red-600 hover:text-red-800"
                                                    title="削除"
                                                >
                                                    <TrashIcon className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>
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
                    {isNew ? "追加" : "決定"}
                </button>
            </div>

            {/* 動作確認モーダル */}
            {checkModalStore && (
                <CheckItemModal
                    itemName={item.name}
                    storeName={checkModalStore.storeName}
                    storeConfig={checkModalStore.storeConfig}
                    onClose={() => setCheckModalStore(null)}
                />
            )}

            {/* Amazon 検索モーダル */}
            {amazonSearchModal && (
                <AmazonSearchModal
                    defaultKeyword={amazonSearchModal.defaultKeyword}
                    onSelect={(asin) => {
                        updateStoreEntry(amazonSearchModal.storeIndex, {
                            ...item.store[amazonSearchModal.storeIndex],
                            asin,
                        });
                    }}
                    onClose={() => setAmazonSearchModal(null)}
                />
            )}
        </form>
    );
}
