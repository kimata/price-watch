/**
 * 価格監視をイメージしたロゴアイコン
 * 虫眼鏡の中に価格トレンドグラフを表示
 */
function PriceWatchLogo({ className }: { className?: string }) {
    return (
        <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className={className}>
            {/* 虫眼鏡のレンズ */}
            <circle cx="26" cy="26" r="18" fill="#dbeafe" stroke="currentColor" strokeWidth="4" />

            {/* レンズ内の価格グラフ */}
            <polyline
                points="14,32 20,28 26,30 32,22 38,26"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
            />

            {/* 虫眼鏡の持ち手 */}
            <line x1="40" y1="40" x2="56" y2="56" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
        </svg>
    );
}

export default function Header() {
    return (
        <header className="bg-white shadow-sm border-b border-gray-200">
            <div className="max-w-7xl mx-auto px-4 py-4">
                <div className="flex items-center gap-3">
                    <PriceWatchLogo className="h-9 w-9 text-blue-600" />
                    <h1 className="text-2xl font-bold text-gray-900">Price Watch</h1>
                </div>
            </div>
        </header>
    );
}
