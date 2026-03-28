interface ChartSkeletonProps {
    className?: string;
}

export default function ChartSkeleton({ className = "h-40" }: ChartSkeletonProps) {
    return (
        <div className={`${className} relative bg-gray-100 rounded flex flex-col justify-between p-4`}>
            {/* 凡例のスケルトン */}
            <div className="flex gap-4 mb-4">
                <div className="h-4 w-16 bg-gray-200 rounded" />
                <div className="h-4 w-20 bg-gray-200 rounded" />
                <div className="h-4 w-14 bg-gray-200 rounded" />
            </div>

            {/* グラフエリアのスケルトン */}
            <div className="flex-1 flex items-end gap-1 opacity-40">
                {Array.from({ length: 20 }).map((_, i) => (
                    <div
                        key={i}
                        className="flex-1 bg-gray-300 rounded-t"
                        style={{
                            height: `${30 + ((i * 7 + 13) % 50)}%`,
                        }}
                    />
                ))}
            </div>

            {/* X軸のスケルトン */}
            <div className="flex justify-between mt-2">
                <div className="h-3 w-12 bg-gray-200 rounded" />
                <div className="h-3 w-12 bg-gray-200 rounded" />
                <div className="h-3 w-12 bg-gray-200 rounded" />
            </div>

            {/* 中央のスピナー */}
            <div className="absolute inset-0 flex items-center justify-center">
                <div className="flex flex-col items-center gap-2">
                    <svg
                        className="h-8 w-8 animate-spin text-gray-400"
                        viewBox="0 0 24 24"
                        fill="none"
                    >
                        <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="3"
                        />
                        <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        />
                    </svg>
                    <span className="text-xs text-gray-400">データ取得中</span>
                </div>
            </div>
        </div>
    );
}
