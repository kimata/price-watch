import { useState, useEffect } from "react";
import { version as reactVersion } from "react";
import { InformationCircleIcon, ChartBarIcon } from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import "dayjs/locale/ja";
import relativeTime from "dayjs/plugin/relativeTime";
import type { StoreDefinition } from "../types";

dayjs.extend(relativeTime);
dayjs.locale("ja");

interface SysInfo {
    date: string;
    timezone: string;
    image_build_date: string | null;
    load_average: string | null;
}

interface FooterProps {
    storeDefinitions: StoreDefinition[];
    onMetricsClick?: () => void;
}

// GitHub アイコン SVG
function GitHubIcon({ className }: { className?: string }) {
    return (
        <svg className={className} viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
        </svg>
    );
}

export default function Footer({ storeDefinitions, onMetricsClick }: FooterProps) {
    const [sysInfo, setSysInfo] = useState<SysInfo | null>(null);
    const buildDate = dayjs(import.meta.env.VITE_BUILD_DATE || new Date());

    // ポイント還元率が設定されているストアのみ表示
    const storesWithPointRate = storeDefinitions.filter((store) => store.point_rate > 0);

    useEffect(() => {
        const fetchSysInfo = async () => {
            try {
                const response = await fetch("/price/api/sysinfo");
                if (response.ok) {
                    const data = await response.json();
                    setSysInfo(data);
                }
            } catch {
                // エラーは無視（フッターなので）
            }
        };

        fetchSysInfo();
        const interval = setInterval(fetchSysInfo, 60000); // 1分ごとに更新
        return () => clearInterval(interval);
    }, []);

    const getImageBuildDate = () => {
        if (!sysInfo?.image_build_date) return "不明";
        const imageBuildDate = dayjs(sysInfo.image_build_date);
        return `${imageBuildDate.format("YYYY年MM月DD日 HH:mm:ss")} [${imageBuildDate.fromNow()}]`;
    };

    return (
        <footer className="mt-8 pb-8">
            <div className="max-w-7xl mx-auto px-4 space-y-4">
                {/* ポイント還元率の説明（ストアがある場合のみ） */}
                {storesWithPointRate.length > 0 && (
                    <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
                        <div className="flex items-start gap-2">
                            <InformationCircleIcon className="h-5 w-5 text-gray-500 flex-shrink-0 mt-0.5" />
                            <div className="space-y-3">
                                <div>
                                    <h3 className="text-sm font-medium text-gray-700 mb-1">
                                        実質価格について
                                    </h3>
                                    <p className="text-xs text-gray-600">
                                        実質価格は、表示価格からポイント還元分を差し引いた価格です。
                                        ポイント還元率はストア毎に以下の値を仮定しています。
                                    </p>
                                </div>
                                <div>
                                    <h3 className="text-sm font-medium text-gray-700 mb-1">
                                        ストア別ポイント還元率
                                    </h3>
                                    <ul className="space-y-1">
                                        {storesWithPointRate.map((store) => (
                                            <li key={store.name} className="text-xs text-gray-600">
                                                <span className="font-medium">{store.name}</span>:{" "}
                                                <span className="font-medium">{store.point_rate}%</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ビルド情報とリンク */}
                <div className="text-right text-sm text-gray-500 space-y-1">
                    <p>イメージビルド: {getImageBuildDate()}</p>
                    <p>
                        React ビルド: {buildDate.format("YYYY年MM月DD日 HH:mm:ss")} [
                        {buildDate.fromNow()}]
                    </p>
                    <p>React バージョン: {reactVersion}</p>
                    <p className="pt-2 flex items-center justify-end gap-3">
                        {/* メトリクスリンク（onMetricsClick が指定されている場合のみ） */}
                        {onMetricsClick && (
                            <button
                                onClick={onMetricsClick}
                                className="text-gray-400 hover:text-gray-600 transition-colors cursor-pointer"
                                title="巡回メトリクス"
                            >
                                <ChartBarIcon className="w-6 h-6" />
                            </button>
                        )}
                        {/* GitHub リンク */}
                        <a
                            href="https://github.com/kimata/price-watch"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-gray-400 hover:text-gray-600 transition-colors"
                            title="GitHub"
                        >
                            <GitHubIcon className="w-6 h-6" />
                        </a>
                    </p>
                </div>
            </div>
        </footer>
    );
}
