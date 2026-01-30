import { useMemo, useCallback } from "react";
import type { Item, StoreDefinition, Period } from "../types";
import ItemCard from "./ItemCard";

interface VirtualizedItemGridProps {
    items: Item[];
    storeDefinitions: StoreDefinition[];
    onItemClick: (item: Item) => void;
    period: Period;
    categories: string[];
    checkIntervalSec?: number;
}

/** カテゴリー名からアンカーIDを生成 */
function categoryToId(category: string): string {
    return `category-${category}`;
}

/**
 * カテゴリー別アイテムグリッド
 *
 * categories の順序に従ってアイテムをカテゴリーごとにグルーピングして表示します。
 * 各カテゴリーの見出しにはパーマリンクアンカーが設定され、
 * ページ上部にカテゴリーナビゲーションリンクが表示されます。
 */
export default function VirtualizedItemGrid({
    items,
    storeDefinitions,
    onItemClick,
    period,
    categories,
    checkIntervalSec = 1800,
}: VirtualizedItemGridProps) {
    const groupedItems = useMemo(() => {
        // アイテムをカテゴリーでグルーピング
        const byCategory = new Map<string, Item[]>();
        for (const item of items) {
            const cat = item.category || "その他";
            const list = byCategory.get(cat);
            if (list) {
                list.push(item);
            } else {
                byCategory.set(cat, [item]);
            }
        }

        // categories の順番に従ってソート済みリストを構築
        const ordered: Array<{ category: string; items: Item[] }> = [];
        const added = new Set<string>();

        for (const cat of categories) {
            const catItems = byCategory.get(cat);
            if (catItems) {
                ordered.push({ category: cat, items: catItems });
                added.add(cat);
            }
        }

        // categories に含まれないカテゴリーを追加（「その他」を除いてアルファベット順）
        const remaining = [...byCategory.keys()]
            .filter((cat) => !added.has(cat) && cat !== "その他")
            .sort();
        for (const cat of remaining) {
            const catItems = byCategory.get(cat);
            if (catItems) {
                ordered.push({ category: cat, items: catItems });
                added.add(cat);
            }
        }

        // 「その他」が categories に含まれていない場合のみ末尾に追加
        if (!added.has("その他")) {
            const otherItems = byCategory.get("その他");
            if (otherItems) {
                ordered.push({ category: "その他", items: otherItems });
            }
        }

        return ordered;
    }, [items, categories]);

    const handleCategoryClick = useCallback((category: string) => {
        const categoryId = categoryToId(category);
        const el = document.getElementById(categoryId);
        if (el) {
            // URL にハッシュを追加（履歴に追加しない）
            const url = new URL(window.location.href);
            url.hash = categoryId;
            window.history.replaceState(window.history.state, "", url.toString());

            el.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    }, []);

    // カテゴリーが1つだけの場合はナビゲーションと見出しを省略
    const showHeaders = groupedItems.length > 1;

    return (
        <div className="space-y-8">
            {showHeaders && (
                <nav className="flex flex-wrap gap-2">
                    {groupedItems.map(({ category }) => (
                        <button
                            key={category}
                            onClick={() => handleCategoryClick(category)}
                            className="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-full hover:bg-gray-50 hover:text-blue-600 hover:border-blue-300 transition-colors"
                        >
                            {category}
                        </button>
                    ))}
                </nav>
            )}

            {groupedItems.map(({ category, items: categoryItems }) => (
                <section key={category} id={categoryToId(category)}>
                    {showHeaders && (
                        <h2 className="text-lg font-semibold text-gray-700 mb-4 border-b border-gray-300 pb-2">
                            <a
                                href={`#${categoryToId(category)}`}
                                className="hover:text-blue-600 transition-colors"
                            >
                                {category}
                            </a>
                        </h2>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {categoryItems.map((item) => (
                            <ItemCard
                                key={item.name}
                                item={item}
                                storeDefinitions={storeDefinitions}
                                onClick={onItemClick}
                                period={period}
                                checkIntervalSec={checkIntervalSec}
                            />
                        ))}
                    </div>
                </section>
            ))}
        </div>
    );
}
