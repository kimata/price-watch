import { useState, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { XMarkIcon, MagnifyingGlassIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import type { AmazonSearchResultItem } from "../../types/config";
import { searchAmazon } from "../../services/configService";

interface AmazonSearchModalProps {
    defaultKeyword: string;
    onSelect: (asin: string) => void;
    onClose: () => void;
}

// レート制限のクールダウン時間（ミリ秒）
const RATE_LIMIT_COOLDOWN_MS = 1500;
// エラー時のリトライ待機時間（ミリ秒）
const ERROR_RETRY_DELAY_MS = 3000;

export default function AmazonSearchModal({
    defaultKeyword,
    onSelect,
    onClose,
}: AmazonSearchModalProps) {
    const [keywords, setKeywords] = useState(defaultKeyword);
    const [results, setResults] = useState<AmazonSearchResultItem[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isRateLimited, setIsRateLimited] = useState(false);
    const [retryCountdown, setRetryCountdown] = useState<number | null>(null);

    const inputRef = useRef<HTMLInputElement>(null);
    const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // クリーンアップ
    useEffect(() => {
        return () => {
            if (retryTimeoutRef.current) {
                clearTimeout(retryTimeoutRef.current);
            }
            if (countdownIntervalRef.current) {
                clearInterval(countdownIntervalRef.current);
            }
        };
    }, []);

    // 初期フォーカス
    useEffect(() => {
        inputRef.current?.focus();
    }, []);

    // 検索実行
    const handleSearch = useCallback(async (isRetry: boolean = false) => {
        if (!keywords.trim()) {
            setError("検索キーワードを入力してください");
            return;
        }

        if (isRateLimited && !isRetry) {
            return;
        }

        setIsLoading(true);
        setError(null);
        setRetryCountdown(null);

        try {
            const response = await searchAmazon(keywords.trim());
            setResults(response.items);

            if (response.items.length === 0) {
                setError("検索結果が見つかりませんでした");
            }

            // 検索成功後、レート制限を適用
            setIsRateLimited(true);
            setTimeout(() => {
                setIsRateLimited(false);
            }, RATE_LIMIT_COOLDOWN_MS);

        } catch (err) {
            const message = err instanceof Error ? err.message : "検索中にエラーが発生しました";
            setError(message);

            // エラー時は3秒後にリトライ
            setRetryCountdown(Math.ceil(ERROR_RETRY_DELAY_MS / 1000));

            // カウントダウン表示
            countdownIntervalRef.current = setInterval(() => {
                setRetryCountdown((prev) => {
                    if (prev === null || prev <= 1) {
                        if (countdownIntervalRef.current) {
                            clearInterval(countdownIntervalRef.current);
                            countdownIntervalRef.current = null;
                        }
                        return null;
                    }
                    return prev - 1;
                });
            }, 1000);

            // 3秒後にリトライ
            retryTimeoutRef.current = setTimeout(() => {
                setRetryCountdown(null);
                handleSearch(true);
            }, ERROR_RETRY_DELAY_MS);
        } finally {
            setIsLoading(false);
        }
    }, [keywords, isRateLimited]);

    // フォーム送信
    const handleSubmit = useCallback((e: React.FormEvent) => {
        e.preventDefault();
        e.stopPropagation();
        // リトライ中のタイマーをキャンセル
        if (retryTimeoutRef.current) {
            clearTimeout(retryTimeoutRef.current);
            retryTimeoutRef.current = null;
        }
        if (countdownIntervalRef.current) {
            clearInterval(countdownIntervalRef.current);
            countdownIntervalRef.current = null;
        }
        setRetryCountdown(null);
        handleSearch();
    }, [handleSearch]);

    // 価格フォーマット
    const formatPrice = (price: number | null): string => {
        if (price === null) return "価格情報なし";
        return `¥${price.toLocaleString()}`;
    };

    // Amazon 商品ページの URL を生成
    const getAmazonUrl = (asin: string): string => {
        return `https://www.amazon.co.jp/dp/${asin}`;
    };

    // 商品選択
    const handleSelect = useCallback((asin: string) => {
        onSelect(asin);
        onClose();
    }, [onSelect, onClose]);

    return createPortal(
        <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
        >
            <div
                className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col"
            >
                {/* ヘッダー */}
                <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
                    <h2 className="text-lg font-medium text-gray-900">
                        Amazon 商品検索
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-2 text-gray-400 hover:text-gray-500 rounded-md"
                    >
                        <XMarkIcon className="w-5 h-5" />
                    </button>
                </div>

                {/* 検索フォーム */}
                <div className="px-6 py-4 border-b border-gray-200">
                    <form onSubmit={handleSubmit} className="flex gap-2">
                        <input
                            ref={inputRef}
                            type="text"
                            value={keywords}
                            onChange={(e) => setKeywords(e.target.value)}
                            placeholder="検索キーワードを入力"
                            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                        <button
                            type="submit"
                            disabled={isLoading || isRateLimited}
                            className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                        >
                            {isLoading ? (
                                <>
                                    <ArrowPathIcon className="w-4 h-4 mr-2 animate-spin" />
                                    検索中
                                </>
                            ) : (
                                <>
                                    <MagnifyingGlassIcon className="w-4 h-4 mr-2" />
                                    検索
                                </>
                            )}
                        </button>
                    </form>
                    {isRateLimited && !isLoading && (
                        <p className="mt-2 text-xs text-gray-500">
                            連続検索を防ぐため、しばらくお待ちください...
                        </p>
                    )}
                </div>

                {/* 検索結果 */}
                <div className="flex-1 overflow-y-auto p-6">
                    {/* エラー表示 */}
                    {error && (
                        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                            <p className="text-sm text-red-700">{error}</p>
                            {retryCountdown !== null && (
                                <p className="mt-1 text-xs text-red-500">
                                    {retryCountdown}秒後にリトライします...
                                </p>
                            )}
                        </div>
                    )}

                    {/* 結果リスト */}
                    {results.length > 0 && (
                        <div className="space-y-3">
                            {results.map((item) => (
                                <div
                                    key={item.asin}
                                    className="flex items-center gap-4 p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
                                >
                                    {/* サムネイル */}
                                    <a
                                        href={getAmazonUrl(item.asin)}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex-shrink-0"
                                    >
                                        {item.thumb_url ? (
                                            <img
                                                src={item.thumb_url}
                                                alt={item.title}
                                                className="w-16 h-16 object-contain border border-gray-200 rounded hover:border-blue-400 transition-colors"
                                            />
                                        ) : (
                                            <div className="w-16 h-16 bg-gray-100 border border-gray-200 rounded flex items-center justify-center text-gray-400 text-xs">
                                                No Image
                                            </div>
                                        )}
                                    </a>

                                    {/* 商品情報 */}
                                    <div className="flex-1 min-w-0">
                                        <a
                                            href={getAmazonUrl(item.asin)}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-sm font-medium text-gray-900 hover:text-blue-600 line-clamp-2 transition-colors"
                                        >
                                            {item.title}
                                        </a>
                                        <div className="mt-1 flex items-center gap-2">
                                            <span className="text-sm font-medium text-orange-600">
                                                {formatPrice(item.price)}
                                            </span>
                                            <span className="text-xs text-gray-400">
                                                ASIN: {item.asin}
                                            </span>
                                        </div>
                                    </div>

                                    {/* 選択ボタン */}
                                    <button
                                        onClick={() => handleSelect(item.asin)}
                                        className="flex-shrink-0 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                                    >
                                        選択
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}

                    {/* 初期状態 */}
                    {results.length === 0 && !error && !isLoading && (
                        <div className="text-center py-12 text-gray-500">
                            <MagnifyingGlassIcon className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                            <p>検索キーワードを入力して検索してください</p>
                        </div>
                    )}
                </div>

                {/* フッター */}
                <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
                    >
                        閉じる
                    </button>
                </div>
            </div>
        </div>,
        document.body
    );
}
