import { useState, useCallback, useEffect } from "react";
import { ExclamationTriangleIcon, ArrowPathIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { previewDeleteRecords, deleteRecords, type DeletePreviewResponse } from "../../services/priceRecordService";
import { useToast } from "../../contexts/ToastContext";
import LoadingSpinner from "../LoadingSpinner";
import { formatPrice } from "../../utils/formatPrice";

interface DeleteConfirmModalProps {
    itemKey: string;
    recordIds: number[];
    requirePassword: boolean;
    priceUnit: string;
    onConfirm: () => void;
    onCancel: () => void;
}

export default function DeleteConfirmModal({
    itemKey,
    recordIds,
    requirePassword,
    priceUnit,
    onConfirm,
    onCancel,
}: DeleteConfirmModalProps) {
    const { showToast } = useToast();
    const [preview, setPreview] = useState<DeletePreviewResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [deleting, setDeleting] = useState(false);
    const [password, setPassword] = useState("");

    // プレビューを取得
    useEffect(() => {
        const fetchPreview = async () => {
            setLoading(true);
            try {
                const response = await previewDeleteRecords(itemKey, recordIds);
                setPreview(response);
            } catch (error) {
                console.error("Failed to get preview:", error);
                showToast("プレビューの取得に失敗しました", "error");
                onCancel();
            } finally {
                setLoading(false);
            }
        };

        fetchPreview();
    }, [itemKey, recordIds, showToast, onCancel]);

    // 削除実行
    const handleDelete = useCallback(async () => {
        if (requirePassword && !password) {
            showToast("パスワードを入力してください", "error");
            return;
        }

        setDeleting(true);
        try {
            const response = await deleteRecords(itemKey, recordIds, password);
            showToast(
                `${response.deleted_records}件の価格記録と${response.deleted_events}件の関連イベントを削除しました`,
                "success"
            );
            onConfirm();
        } catch (error: unknown) {
            console.error("Failed to delete records:", error);
            // 401 エラーの場合はパスワードエラー
            if (error && typeof error === "object" && "response" in error) {
                const axiosError = error as { response?: { status?: number; data?: { error?: string } } };
                if (axiosError.response?.status === 401) {
                    showToast("パスワードが正しくありません", "error");
                    return;
                }
                if (axiosError.response?.data?.error) {
                    showToast(axiosError.response.data.error, "error");
                    return;
                }
            }
            showToast("削除に失敗しました", "error");
        } finally {
            setDeleting(false);
        }
    }, [itemKey, recordIds, password, requirePassword, showToast, onConfirm]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
            {/* オーバーレイ */}
            <div className="fixed inset-0 bg-black/50" onClick={onCancel} />

            {/* モーダル */}
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
                {/* 閉じるボタン */}
                <button
                    onClick={onCancel}
                    className="absolute top-4 right-4 p-1 rounded-md hover:bg-gray-100 transition-colors cursor-pointer"
                >
                    <XMarkIcon className="w-5 h-5 text-gray-500" />
                </button>

                {/* ヘッダー */}
                <div className="flex items-center gap-3 mb-4">
                    <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                        <ExclamationTriangleIcon className="w-6 h-6 text-red-600" />
                    </div>
                    <h2 className="text-lg font-semibold text-gray-900">
                        価格記録の削除
                    </h2>
                </div>

                {loading ? (
                    <div className="flex justify-center py-8">
                        <LoadingSpinner />
                    </div>
                ) : preview ? (
                    <>
                        {/* プレビュー情報 */}
                        <div className="bg-gray-50 rounded-lg p-4 mb-4 space-y-2">
                            <div className="flex justify-between text-sm">
                                <span className="text-gray-600">削除対象レコード:</span>
                                <span className="font-medium text-red-600">{preview.record_count}件</span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <span className="text-gray-600">削除される関連イベント:</span>
                                <span className="font-medium text-red-600">{preview.event_count}件</span>
                            </div>
                            {preview.prices.length > 0 && (
                                <div className="pt-2 border-t border-gray-200 text-sm">
                                    <span className="text-gray-600">対象価格: </span>
                                    <span className="text-gray-900">
                                        {preview.prices.map((p) => formatPrice(p, priceUnit)).join(", ")}
                                    </span>
                                </div>
                            )}
                        </div>

                        <p className="text-sm text-gray-600 mb-4">
                            この操作は取り消せません。選択した価格記録と、同じ価格を持つ関連イベント（LOWEST_PRICE, PRICE_DROP）が削除されます。
                        </p>

                        {/* パスワード入力 */}
                        {requirePassword && (
                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    パスワード
                                </label>
                                <input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    placeholder="パスワードを入力"
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") {
                                            handleDelete();
                                        }
                                    }}
                                />
                            </div>
                        )}

                        {/* ボタン */}
                        <div className="flex justify-end gap-3">
                            <button
                                onClick={onCancel}
                                disabled={deleting}
                                className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50 cursor-pointer"
                            >
                                キャンセル
                            </button>
                            <button
                                onClick={handleDelete}
                                disabled={deleting || (requirePassword && !password)}
                                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                            >
                                {deleting && <ArrowPathIcon className="w-4 h-4 animate-spin" />}
                                {deleting ? "削除中..." : "削除する"}
                            </button>
                        </div>
                    </>
                ) : null}
            </div>
        </div>
    );
}
