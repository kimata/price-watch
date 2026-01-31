import { useState } from "react";

interface SaveConfirmModalProps {
    createBackup: boolean;
    onCreateBackupChange: (value: boolean) => void;
    onConfirm: (password?: string) => void;
    onCancel: () => void;
    saving: boolean;
    requirePassword: boolean;
}

export default function SaveConfirmModal({
    createBackup,
    onCreateBackupChange,
    onConfirm,
    onCancel,
    saving,
    requirePassword,
}: SaveConfirmModalProps) {
    const [password, setPassword] = useState("");

    const handleConfirm = () => {
        onConfirm(requirePassword ? password : undefined);
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">
                    設定を保存しますか？
                </h2>
                <p className="text-sm text-gray-600 mb-4">
                    target.yaml に変更を保存します。
                </p>

                {requirePassword && (
                    <div className="mb-4">
                        <label htmlFor="save-password" className="block text-sm font-medium text-gray-700 mb-1">
                            パスワード
                        </label>
                        <input
                            type="password"
                            id="save-password"
                            name="password"
                            autoComplete="current-password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="パスワードを入力"
                            className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            autoFocus
                        />
                    </div>
                )}

                <label className="flex items-center gap-2 mb-6">
                    <input
                        type="checkbox"
                        checked={createBackup}
                        onChange={(e) => onCreateBackupChange(e.target.checked)}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-700">
                        バックアップを作成する
                    </span>
                </label>
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onCancel}
                        disabled={saving}
                        className="px-4 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded-md transition-colors disabled:opacity-50"
                    >
                        キャンセル
                    </button>
                    <button
                        onClick={handleConfirm}
                        disabled={saving || (requirePassword && !password)}
                        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 transition-colors"
                    >
                        {saving ? "保存中..." : "保存"}
                    </button>
                </div>
            </div>
        </div>
    );
}
