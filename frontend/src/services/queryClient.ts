import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            // SSE更新があるため短めのstaleTime
            staleTime: 30 * 1000, // 30秒
            // ガベージコレクション時間
            gcTime: 5 * 60 * 1000, // 5分
            // ウィンドウフォーカス時の再フェッチを無効化（SSEで更新されるため）
            refetchOnWindowFocus: false,
            // 接続時の再フェッチを無効化
            refetchOnReconnect: false,
            // リトライ設定
            retry: 1,
            retryDelay: 1000,
        },
    },
});
