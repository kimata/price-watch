interface HatenaBookmarkIconProps {
    className?: string;
}

export default function HatenaBookmarkIcon({ className }: HatenaBookmarkIconProps) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="currentColor">
            {/* はてなブックマークの "B!" ロゴ */}
            <rect x="2" y="2" width="20" height="20" rx="3" />
            <text
                x="12"
                y="17"
                textAnchor="middle"
                fontSize="14"
                fontWeight="bold"
                fontFamily="Arial, sans-serif"
                fill="white"
            >
                B!
            </text>
        </svg>
    );
}
