import { useMemo, useCallback, useRef, useLayoutEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Item, StoreDefinition, Period } from "../types";
import ItemCard from "./ItemCard";
import PermalinkHeading from "./PermalinkHeading";

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

// 行のタイプ
type RowType =
    | { type: "header"; category: string }
    | { type: "items"; items: Item[] };

// レスポンシブカラム数
function getColumnCount(): number {
    if (typeof window === "undefined") return 1;
    const width = window.innerWidth;
    if (width >= 1024) return 3; // lg
    if (width >= 768) return 2; // md
    return 1;
}

/**
 * カテゴリー別アイテムグリッド（仮想スクロール対応）
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
    const parentRef = useRef<HTMLDivElement>(null);
    const columnCountRef = useRef(getColumnCount());

    // ウィンドウリサイズ時にカラム数を更新
    useLayoutEffect(() => {
        const handleResize = () => {
            const newColumnCount = getColumnCount();
            if (columnCountRef.current !== newColumnCount) {
                columnCountRef.current = newColumnCount;
                // 仮想化を再計算
                virtualizer.measure();
            }
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    });

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

    // 仮想スクロールのしきい値（アイテム数がこれ以上なら仮想化）
    const VIRTUALIZATION_THRESHOLD = 30;
    const shouldVirtualize = items.length >= VIRTUALIZATION_THRESHOLD;

    // カテゴリーが1つだけの場合はナビゲーションと見出しを省略
    const showHeaders = groupedItems.length > 1;

    // フラット化した行データを生成
    const rows = useMemo(() => {
        const result: RowType[] = [];
        const columnCount = columnCountRef.current;

        for (const { category, items: categoryItems } of groupedItems) {
            // カテゴリーヘッダー（複数カテゴリーの場合のみ）
            if (showHeaders) {
                result.push({ type: "header", category });
            }

            // アイテムを行ごとにグルーピング
            for (let i = 0; i < categoryItems.length; i += columnCount) {
                const rowItems = categoryItems.slice(i, i + columnCount);
                result.push({ type: "items", items: rowItems });
            }
        }

        return result;
    }, [groupedItems, showHeaders]);

    // 行の高さを推定
    const estimateSize = useCallback(
        (index: number): number => {
            const row = rows[index];
            if (row.type === "header") {
                return 56; // ヘッダーの高さ
            }
            // アイテム行の高さ（カードの高さ + gap）
            return 400;
        },
        [rows]
    );

    const virtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => parentRef.current,
        estimateSize,
        overscan: 3,
    });

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

    // アイテム数が少ない場合は従来のレンダリングを使用
    if (!shouldVirtualize) {
        return (
            <div className="space-y-8">
                {showHeaders && (
                    <nav className="flex flex-wrap gap-2">
                        {groupedItems.map(({ category }) => (
                            <button
                                key={category}
                                onClick={() => handleCategoryClick(category)}
                                className="px-3 py-1.5 text-sm font-medium text-gray-600 bg-white border border-gray-300 rounded-full hover:bg-gray-50 hover:text-blue-600 hover:border-blue-300 transition-colors cursor-pointer"
                            >
                                {category}
                            </button>
                        ))}
                    </nav>
                )}

                {groupedItems.map(({ category, items: categoryItems }) => (
                    <section key={category}>
                        {showHeaders && (
                            <PermalinkHeading
                                id={categoryToId(category)}
                                className="text-lg font-semibold text-gray-700 mb-4 border-b border-gray-300 pb-2"
                            >
                                {category}
                            </PermalinkHeading>
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

    // 仮想スクロール版
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

            <div
                ref={parentRef}
                style={{
                    height: "calc(100vh - 200px)",
                    overflow: "auto",
                }}
            >
                <div
                    style={{
                        height: `${virtualizer.getTotalSize()}px`,
                        width: "100%",
                        position: "relative",
                    }}
                >
                    {virtualizer.getVirtualItems().map((virtualRow) => {
                        const row = rows[virtualRow.index];

                        if (row.type === "header") {
                            return (
                                <div
                                    key={virtualRow.key}
                                    style={{
                                        position: "absolute",
                                        top: 0,
                                        left: 0,
                                        width: "100%",
                                        height: `${virtualRow.size}px`,
                                        transform: `translateY(${virtualRow.start}px)`,
                                    }}
                                >
                                    <PermalinkHeading
                                        id={categoryToId(row.category)}
                                        className="text-lg font-semibold text-gray-700 mb-4 border-b border-gray-300 pb-2"
                                    >
                                        {row.category}
                                    </PermalinkHeading>
                                </div>
                            );
                        }

                        return (
                            <div
                                key={virtualRow.key}
                                style={{
                                    position: "absolute",
                                    top: 0,
                                    left: 0,
                                    width: "100%",
                                    transform: `translateY(${virtualRow.start}px)`,
                                    paddingBottom: "24px",
                                }}
                            >
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                                    {row.items.map((item) => (
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
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
