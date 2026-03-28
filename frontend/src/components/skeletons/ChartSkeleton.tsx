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
                <div className="flex flex-col items-center gap-3">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-400" />
                    <span className="text-xs text-gray-400">データ取得中</span>
                </div>
            </div>
        </div>
    );
}
