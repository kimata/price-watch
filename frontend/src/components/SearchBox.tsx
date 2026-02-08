import { useState, useCallback, useRef, useEffect, type KeyboardEvent } from "react";
import { MagnifyingGlassIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { useSearch } from "../hooks/useSearch";
import type { Item } from "../types";

interface SearchBoxProps {
    items: Item[];
    onItemClick: (item: Item) => void;
    isMobile?: boolean;
    onClose?: () => void;
}

export default function SearchBox({ items, onItemClick, isMobile = false, onClose }: SearchBoxProps) {
    const [query, setQuery] = useState("");
    const [isOpen, setIsOpen] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(-1);
    const inputRef = useRef<HTMLInputElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    const { results, isSearching } = useSearch(query, items);

    // 外部クリックで閉じる
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };

        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    // 検索結果が変わったらインデックスをリセット
    useEffect(() => {
        setSelectedIndex(-1);
    }, [results]);

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        setQuery(e.target.value);
        setIsOpen(true);
    }, []);

    const handleItemClick = useCallback(
        (item: Item) => {
            onItemClick(item);
            setQuery("");
            setIsOpen(false);
            onClose?.();
        },
        [onItemClick, onClose]
    );

    const handleKeyDown = useCallback(
        (e: KeyboardEvent<HTMLInputElement>) => {
            if (!isOpen || results.length === 0) return;

            switch (e.key) {
                case "ArrowDown":
                    e.preventDefault();
                    setSelectedIndex((prev) => (prev < results.length - 1 ? prev + 1 : prev));
                    break;
                case "ArrowUp":
                    e.preventDefault();
                    setSelectedIndex((prev) => (prev > 0 ? prev - 1 : -1));
                    break;
                case "Enter":
                    e.preventDefault();
                    if (selectedIndex >= 0 && results[selectedIndex]) {
                        handleItemClick(results[selectedIndex]);
                    }
                    break;
                case "Escape":
                    setIsOpen(false);
                    inputRef.current?.blur();
                    break;
            }
        },
        [isOpen, results, selectedIndex, handleItemClick]
    );

    const handleClear = useCallback(() => {
        setQuery("");
        setIsOpen(false);
        inputRef.current?.focus();
    }, []);

    const showResults = isOpen && query.trim() && (results.length > 0 || isSearching);

    return (
        <div ref={containerRef} className={`relative ${isMobile ? "w-full" : "w-64"}`}>
            <div className="relative">
                <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={handleInputChange}
                    onFocus={() => query.trim() && setIsOpen(true)}
                    onKeyDown={handleKeyDown}
                    placeholder="アイテムを検索..."
                    className="w-full pl-9 pr-8 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
                {query && (
                    <button
                        type="button"
                        onClick={handleClear}
                        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 cursor-pointer"
                    >
                        <XMarkIcon className="h-4 w-4" />
                    </button>
                )}
            </div>

            {/* 検索結果ドロップダウン */}
            {showResults && (
                <div className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-80 overflow-auto">
                    {isSearching ? (
                        <div className="px-4 py-3 text-sm text-gray-500">検索中...</div>
                    ) : results.length === 0 ? (
                        <div className="px-4 py-3 text-sm text-gray-500">該当するアイテムがありません</div>
                    ) : (
                        <ul>
                            {results.map((item, index) => (
                                <li key={item.stores[0]?.item_key ?? item.name}>
                                    <button
                                        type="button"
                                        onClick={() => handleItemClick(item)}
                                        className={`w-full text-left px-4 py-3 flex items-center gap-3 transition-colors cursor-pointer ${
                                            index === selectedIndex
                                                ? "bg-blue-50"
                                                : "hover:bg-gray-50"
                                        }`}
                                    >
                                        {item.thumb_url ? (
                                            <img
                                                src={item.thumb_url}
                                                alt=""
                                                className="w-10 h-10 object-cover rounded flex-shrink-0"
                                            />
                                        ) : (
                                            <div className="w-10 h-10 bg-gray-100 rounded flex-shrink-0 flex items-center justify-center">
                                                <span className="text-gray-400 text-xs">No Image</span>
                                            </div>
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm font-medium text-gray-900 truncate">
                                                {item.name}
                                            </div>
                                            {item.best_effective_price !== null && (
                                                <div className="text-xs text-gray-500">
                                                    最安 {item.best_effective_price.toLocaleString()}円
                                                </div>
                                            )}
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}
