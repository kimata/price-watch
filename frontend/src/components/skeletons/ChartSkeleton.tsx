interface ChartSkeletonProps {
    className?: string;
}

export default function ChartSkeleton({ className = "h-40" }: ChartSkeletonProps) {
    return (
        <div className={`${className} bg-gray-100 rounded animate-pulse flex flex-col justify-between p-4`}>
            {/* 凡例のスケルトン */}
            <div className="flex gap-4 mb-4">
                <div className="h-4 w-16 bg-gray-200 rounded" />
                <div className="h-4 w-20 bg-gray-200 rounded" />
                <div className="h-4 w-14 bg-gray-200 rounded" />
            </div>

            {/* グラフエリアのスケルトン */}
            <div className="flex-1 flex items-end gap-1">
                {Array.from({ length: 20 }).map((_, i) => (
                    <div
                        key={i}
                        className="flex-1 bg-gray-200 rounded-t"
                        style={{
                            height: `${30 + Math.random() * 50}%`,
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
        </div>
    );
}
