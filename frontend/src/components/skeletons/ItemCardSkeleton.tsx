export default function ItemCardSkeleton() {
    return (
        <div className="bg-white rounded-lg shadow-md border border-gray-200 overflow-hidden flex flex-col h-full animate-pulse">
            <div className="p-4">
                <div className="flex gap-4">
                    {/* サムネイルのスケルトン */}
                    <div className="w-20 h-20 bg-gray-200 rounded-md flex-shrink-0" />

                    <div className="flex-1 min-w-0">
                        {/* タイトルのスケルトン */}
                        <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                        <div className="h-4 bg-gray-200 rounded w-1/2 mb-3" />

                        {/* 価格のスケルトン */}
                        <div className="flex items-center gap-2">
                            <div className="h-6 bg-gray-200 rounded w-24" />
                            <div className="h-4 bg-gray-200 rounded w-16" />
                        </div>
                    </div>
                </div>

                {/* ストア一覧のスケルトン */}
                <div className="mt-4 space-y-2">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <div
                            key={i}
                            className="flex items-center justify-between py-2 px-3 bg-gray-100 rounded-md"
                        >
                            <div className="h-4 bg-gray-200 rounded w-20" />
                            <div className="flex items-center gap-2">
                                <div className="h-4 bg-gray-200 rounded w-16" />
                                <div className="h-5 w-5 bg-gray-200 rounded-full" />
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* グラフエリアのスケルトン */}
            <div className="mt-auto">
                <div className="px-4 pb-4">
                    <div className="h-40 bg-gray-100 rounded" />
                </div>

                {/* フッターのスケルトン */}
                <div className="px-4 py-2 bg-gray-50 border-t border-gray-100 flex items-center gap-1">
                    <div className="h-3.5 w-3.5 bg-gray-200 rounded" />
                    <div className="h-3 bg-gray-200 rounded w-32" />
                </div>
            </div>
        </div>
    );
}
