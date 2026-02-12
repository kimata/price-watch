import { useState, memo } from "react";

interface ChartImageProps {
    itemKey: string;
    className?: string;
}

/**
 * トップページ用チャート画像コンポーネント
 *
 * サーバーで事前生成された画像を表示する。
 * - 画像は /price/chart/{item_key}.png から取得
 * - 3時間キャッシュ（Cache-Control: max-age=10800）
 */
function ChartImage({ itemKey, className = "" }: ChartImageProps) {
    const [isLoading, setIsLoading] = useState(true);
    const [hasError, setHasError] = useState(false);

    const imageUrl = `/price/chart/${encodeURIComponent(itemKey)}.png`;

    const handleLoad = () => {
        setIsLoading(false);
    };

    const handleError = () => {
        setIsLoading(false);
        setHasError(true);
    };

    if (hasError) {
        return (
            <div className={`flex items-center justify-center bg-gray-50 rounded ${className}`}>
                <span className="text-gray-400 text-xs">グラフを読み込めませんでした</span>
            </div>
        );
    }

    return (
        <div className={`relative ${className}`}>
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-gray-50 rounded">
                    <div className="animate-pulse flex items-center gap-2">
                        <div className="w-4 h-4 bg-gray-200 rounded-full"></div>
                        <span className="text-gray-400 text-xs">読み込み中...</span>
                    </div>
                </div>
            )}
            <img
                src={imageUrl}
                alt="価格推移グラフ"
                className={`w-full h-full object-contain rounded ${isLoading ? "opacity-0" : "opacity-100"} transition-opacity duration-200`}
                onLoad={handleLoad}
                onError={handleError}
                loading="lazy"
            />
        </div>
    );
}

export default memo(ChartImage);
