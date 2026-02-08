import { useState, useEffect } from "react";
import XIcon from "./icons/XIcon";
import LineIcon from "./icons/LineIcon";
import HatenaBookmarkIcon from "./icons/HatenaBookmarkIcon";

interface ShareButtonsProps {
    title: string;
    text?: string;
}

// はてなブックマーク数を取得
function useHatenaBookmarkCount(url: string): number | null {
    const [count, setCount] = useState<number | null>(null);

    useEffect(() => {
        const fetchCount = async () => {
            try {
                const response = await fetch(
                    `https://bookmark.hatenaapis.com/count/entry?url=${encodeURIComponent(url)}`
                );
                if (response.ok) {
                    const data = await response.json();
                    if (typeof data === "number" && data > 0) {
                        setCount(data);
                    }
                }
            } catch {
                // エラーは無視
            }
        };
        fetchCount();
    }, [url]);

    return count;
}

export default function ShareButtons({ title, text }: ShareButtonsProps) {
    const currentUrl = window.location.href;
    const shareText = text ?? title;
    const hatenaCount = useHatenaBookmarkCount(currentUrl);

    // X (Twitter) シェアURL
    const xUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(shareText)}&url=${encodeURIComponent(currentUrl)}`;

    // LINE シェアURL
    const lineUrl = `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(currentUrl)}`;

    // はてなブックマーク追加URL
    const hatenaUrl = `https://b.hatena.ne.jp/entry/panel/?url=${encodeURIComponent(currentUrl)}&btitle=${encodeURIComponent(title)}`;

    return (
        <div className="flex items-center gap-1">
            {/* X (Twitter) */}
            <a
                href={xUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-2 py-1 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded transition-colors"
                title="X (Twitter) で共有"
            >
                <XIcon className="h-4 w-4" />
            </a>

            {/* LINE */}
            <a
                href={lineUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-2 py-1 text-gray-500 hover:text-[#00B900] hover:bg-green-50 rounded transition-colors"
                title="LINE で共有"
            >
                <LineIcon className="h-4 w-4" />
            </a>

            {/* はてなブックマーク */}
            <a
                href={hatenaUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 px-2 py-1 text-gray-500 hover:text-[#00A4DE] hover:bg-blue-50 rounded transition-colors"
                title="はてなブックマークに追加"
            >
                <HatenaBookmarkIcon className="h-4 w-4" />
                {hatenaCount !== null && (
                    <span className="text-xs text-gray-400">{hatenaCount}</span>
                )}
            </a>
        </div>
    );
}
