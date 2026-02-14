import { BellIcon, BellAlertIcon, BellSlashIcon } from "@heroicons/react/24/outline";
import { BellIcon as BellIconSolid } from "@heroicons/react/24/solid";
import { usePushNotification } from "../hooks/usePushNotification";

interface PushNotificationButtonProps {
    itemKey: string;
    size?: "sm" | "md" | "lg";
    showLabel?: boolean;
}

export default function PushNotificationButton({
    itemKey,
    size = "md",
    showLabel = false,
}: PushNotificationButtonProps) {
    const {
        isSupported,
        isLoading,
        isSubscribed,
        subscriptionCount,
        error,
        subscribe,
        unsubscribe,
        permission,
    } = usePushNotification(itemKey);

    // ブラウザがサポートしていない場合は表示しない
    if (!isSupported) {
        return null;
    }

    const handleClick = async () => {
        if (isSubscribed) {
            await unsubscribe();
        } else {
            await subscribe();
        }
    };

    // サイズに応じたクラス
    const sizeClasses = {
        sm: "p-1.5",
        md: "p-2",
        lg: "p-2.5",
    };

    const iconSizeClasses = {
        sm: "h-4 w-4",
        md: "h-5 w-5",
        lg: "h-6 w-6",
    };

    // 権限が拒否されている場合
    if (permission === "denied") {
        return (
            <div className="relative group">
                <button
                    disabled
                    className={`${sizeClasses[size]} rounded-full bg-gray-100 text-gray-400 cursor-not-allowed flex items-center gap-2`}
                    title="通知がブロックされています"
                >
                    <BellSlashIcon className={iconSizeClasses[size]} />
                    {showLabel && <span className="text-sm">通知ブロック中</span>}
                </button>
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-800 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                    ブラウザの設定で通知がブロックされています
                </div>
            </div>
        );
    }

    return (
        <div className="relative group">
            <button
                onClick={handleClick}
                disabled={isLoading}
                className={`${sizeClasses[size]} rounded-full transition-colors cursor-pointer flex items-center gap-2 ${
                    isSubscribed
                        ? "bg-blue-100 text-blue-600 hover:bg-blue-200"
                        : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                } ${isLoading ? "opacity-50 cursor-wait" : ""}`}
                title={isSubscribed ? "通知を解除" : "通知を受け取る"}
            >
                {isLoading ? (
                    <div className={`${iconSizeClasses[size]} animate-spin`}>
                        <svg className="w-full h-full" viewBox="0 0 24 24">
                            <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="none"
                            />
                            <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            />
                        </svg>
                    </div>
                ) : isSubscribed ? (
                    <BellIconSolid className={iconSizeClasses[size]} />
                ) : (
                    <BellIcon className={iconSizeClasses[size]} />
                )}
                {showLabel && (
                    <span className="text-sm">
                        {isSubscribed ? "通知ON" : "通知OFF"}
                    </span>
                )}
            </button>

            {/* ツールチップ */}
            <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-gray-800 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-20">
                {isSubscribed ? (
                    <>
                        <div className="flex items-center gap-1 mb-1">
                            <BellAlertIcon className="h-3 w-3" />
                            <span>通知を受け取り中</span>
                        </div>
                        <div className="text-gray-300 text-[10px]">
                            価格下落・最安値更新・在庫復活時に通知
                        </div>
                        {subscriptionCount > 1 && (
                            <div className="text-gray-400 text-[10px] mt-1">
                                {subscriptionCount}台のデバイスで登録中
                            </div>
                        )}
                    </>
                ) : (
                    <>
                        <div>クリックして通知を受け取る</div>
                        <div className="text-gray-300 text-[10px]">
                            価格下落・最安値更新・在庫復活を通知
                        </div>
                    </>
                )}
            </div>

            {/* エラー表示 */}
            {error && (
                <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 bg-red-100 text-red-600 text-xs rounded-lg whitespace-nowrap z-20">
                    {error}
                </div>
            )}
        </div>
    );
}
