import { useState, useCallback } from "react";
import { LinkIcon, CheckIcon } from "@heroicons/react/24/outline";
import { useToast } from "../contexts/ToastContext";

interface PermalinkHeadingProps {
    id: string;
    children: React.ReactNode;
    as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
    className?: string;
}

/**
 * Permalink 対応の見出しコンポーネント
 *
 * ホバー時にリンクアイコンを表示し、クリックで permalink をコピー
 */
export default function PermalinkHeading({
    id,
    children,
    as: Tag = "h2",
    className = "",
}: PermalinkHeadingProps) {
    const [copied, setCopied] = useState(false);
    const { showToast } = useToast();

    const handleCopyLink = useCallback(async () => {
        const url = new URL(window.location.href);
        url.hash = id;
        try {
            await navigator.clipboard.writeText(url.toString());
            setCopied(true);
            showToast("リンクをコピーしました");
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error("Failed to copy link:", err);
        }
    }, [id, showToast]);

    return (
        <Tag id={id} className={`group ${className}`}>
            <a
                href={`#${id}`}
                className="inline-flex items-center gap-2 hover:text-blue-600 transition-colors"
                onClick={(e) => {
                    e.preventDefault();
                    handleCopyLink();
                    // スクロールも行う
                    const el = document.getElementById(id);
                    if (el) {
                        el.scrollIntoView({ behavior: "smooth", block: "start" });
                    }
                }}
            >
                {children}
            </a>
            <button
                onClick={handleCopyLink}
                className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity align-middle inline-flex items-center text-gray-400 hover:text-blue-600"
                title="リンクをコピー"
                aria-label="リンクをコピー"
            >
                {copied ? (
                    <CheckIcon className="h-4 w-4 text-green-500" />
                ) : (
                    <LinkIcon className="h-4 w-4" />
                )}
            </button>
        </Tag>
    );
}
