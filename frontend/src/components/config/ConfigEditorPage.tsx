import { useState, useEffect, useCallback } from "react";
import { ArrowLeftIcon, ArrowPathIcon } from "@heroicons/react/24/outline";
import type { TargetConfig, ValidationError } from "../../types/config";
import { fetchTargetConfig, updateTargetConfig, validateTargetConfig } from "../../services/configService";
import { useToast } from "../../contexts/ToastContext";
import LoadingSpinner from "../LoadingSpinner";
import ConfigTabs from "./ConfigTabs";
import StoresTab from "./StoresTab";
import CategoriesTab from "./CategoriesTab";
import ItemsTab from "./ItemsTab";
import SaveConfirmModal from "./SaveConfirmModal";

interface ConfigEditorPageProps {
    onBack: () => void;
}

type TabType = "stores" | "categories" | "items";

export default function ConfigEditorPage({ onBack }: ConfigEditorPageProps) {
    const { showToast } = useToast();
    const [config, setConfig] = useState<TargetConfig | null>(null);
    const [originalConfig, setOriginalConfig] = useState<TargetConfig | null>(null);
    const [checkMethods, setCheckMethods] = useState<string[]>([]);
    const [actionTypes, setActionTypes] = useState<string[]>([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
    const [activeTab, setActiveTab] = useState<TabType>("items");
    const [showSaveModal, setShowSaveModal] = useState(false);
    const [createBackup, setCreateBackup] = useState(true);
    const [requirePassword, setRequirePassword] = useState(false);

    // 変更があるかどうかを判定
    const hasChanges = useCallback(() => {
        if (!config || !originalConfig) return false;
        return JSON.stringify(config) !== JSON.stringify(originalConfig);
    }, [config, originalConfig]);

    // 設定を読み込み
    const loadConfig = useCallback(async () => {
        setLoading(true);
        try {
            const response = await fetchTargetConfig();
            setConfig(response.config);
            setOriginalConfig(JSON.parse(JSON.stringify(response.config)));
            setCheckMethods(response.check_methods);
            setActionTypes(response.action_types);
            setRequirePassword(response.require_password);
            setValidationErrors([]);
        } catch (error) {
            console.error("Failed to load config:", error);
            showToast("設定の読み込みに失敗しました", "error");
        } finally {
            setLoading(false);
        }
    }, [showToast]);

    useEffect(() => {
        loadConfig();
    }, [loadConfig]);

    // バリデーション
    const validate = useCallback(async () => {
        if (!config) return false;
        try {
            const response = await validateTargetConfig(config);
            setValidationErrors(response.errors);
            return response.valid;
        } catch (error) {
            console.error("Validation failed:", error);
            showToast("バリデーションに失敗しました", "error");
            return false;
        }
    }, [config, showToast]);

    // 保存処理
    const handleSave = useCallback(async (password?: string) => {
        if (!config) return;

        // まずバリデーション
        const isValid = await validate();
        if (!isValid) {
            showToast("設定にエラーがあります", "error");
            setShowSaveModal(false);
            return;
        }

        setSaving(true);
        try {
            const result = await updateTargetConfig(config, createBackup, password);
            setOriginalConfig(JSON.parse(JSON.stringify(config)));
            setValidationErrors([]);

            // Git push の結果に応じてメッセージを変更
            if (result.git_pushed) {
                showToast("設定を保存し、Git にプッシュしました", "success");
            } else {
                showToast("設定を保存しました", "success");
            }
            setShowSaveModal(false);
        } catch (error: unknown) {
            console.error("Failed to save config:", error);
            // 401 エラーの場合はパスワードエラーを表示
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
            showToast("設定の保存に失敗しました", "error");
        } finally {
            setSaving(false);
        }
    }, [config, createBackup, validate, showToast]);

    // リセット処理
    const handleReset = useCallback(() => {
        if (originalConfig) {
            setConfig(JSON.parse(JSON.stringify(originalConfig)));
            setValidationErrors([]);
            showToast("変更を取り消しました", "info");
        }
    }, [originalConfig, showToast]);

    // 設定変更ハンドラ
    const handleConfigChange = useCallback((newConfig: TargetConfig) => {
        setConfig(newConfig);
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-100 flex items-center justify-center">
                <LoadingSpinner />
            </div>
        );
    }

    if (!config) {
        return (
            <div className="min-h-screen bg-gray-100 flex items-center justify-center">
                <div className="text-center">
                    <p className="text-red-600 mb-4">設定の読み込みに失敗しました</p>
                    <button
                        onClick={loadConfig}
                        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                    >
                        再読み込み
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-100">
            {/* ヘッダー */}
            <header className="bg-white shadow-sm sticky top-0 z-10">
                <div className="max-w-7xl mx-auto px-4 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <button
                                onClick={onBack}
                                className="p-2 rounded-md hover:bg-gray-100 transition-colors"
                                title="戻る"
                            >
                                <ArrowLeftIcon className="w-5 h-5 text-gray-600" />
                            </button>
                            <h1 className="text-xl font-semibold text-gray-900">
                                設定エディタ
                            </h1>
                            {hasChanges() && (
                                <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded-full">
                                    未保存の変更あり
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={loadConfig}
                                disabled={loading}
                                className="p-2 rounded-md hover:bg-gray-100 transition-colors disabled:opacity-50"
                                title="再読み込み"
                            >
                                <ArrowPathIcon className={`w-5 h-5 text-gray-600 ${loading ? "animate-spin" : ""}`} />
                            </button>
                            {hasChanges() && (
                                <button
                                    onClick={handleReset}
                                    className="px-3 py-1.5 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-md transition-colors"
                                >
                                    変更を取り消す
                                </button>
                            )}
                            <button
                                onClick={() => setShowSaveModal(true)}
                                disabled={!hasChanges() || saving}
                                className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                {saving ? "保存中..." : "保存"}
                            </button>
                        </div>
                    </div>
                </div>
            </header>

            {/* バリデーションエラー表示 */}
            {validationErrors.length > 0 && (
                <div className="max-w-7xl mx-auto px-4 py-2">
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <h3 className="text-sm font-medium text-red-800 mb-2">
                            設定にエラーがあります
                        </h3>
                        <ul className="list-disc list-inside text-sm text-red-700 space-y-1">
                            {validationErrors.map((error, index) => (
                                <li key={index}>
                                    <span className="font-mono text-xs">{error.path}</span>: {error.message}
                                </li>
                            ))}
                        </ul>
                    </div>
                </div>
            )}

            {/* タブ */}
            <div className="max-w-7xl mx-auto px-4 py-4">
                <ConfigTabs activeTab={activeTab} onChange={setActiveTab} />
            </div>

            {/* タブコンテンツ */}
            <main className="max-w-7xl mx-auto px-4 pb-8">
                {activeTab === "stores" && (
                    <StoresTab
                        config={config}
                        onChange={handleConfigChange}
                        checkMethods={checkMethods}
                        actionTypes={actionTypes}
                    />
                )}
                {activeTab === "categories" && (
                    <CategoriesTab
                        config={config}
                        onChange={handleConfigChange}
                    />
                )}
                {activeTab === "items" && (
                    <ItemsTab
                        config={config}
                        onChange={handleConfigChange}
                    />
                )}
            </main>

            {/* 保存確認モーダル */}
            {showSaveModal && (
                <SaveConfirmModal
                    createBackup={createBackup}
                    onCreateBackupChange={setCreateBackup}
                    onConfirm={handleSave}
                    onCancel={() => setShowSaveModal(false)}
                    saving={saving}
                    requirePassword={requirePassword}
                />
            )}
        </div>
    );
}
