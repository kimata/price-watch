import { useMemo } from "react";
import {
    BuildingStorefrontIcon,
    ChartBarIcon,
    BellAlertIcon,
    ClockIcon,
} from "@heroicons/react/24/outline";
import dayjs from "dayjs";
import type { Item, StoreDefinition } from "../types";
import SearchBox from "./SearchBox";

interface HeroSectionProps {
    items: Item[];
    storeDefinitions: StoreDefinition[];
    onItemClick: (item: Item) => void;
}

export default function HeroSection({ items, storeDefinitions, onItemClick }: HeroSectionProps) {
    // 統計情報を計算
    const stats = useMemo(() => {
        const itemCount = items.length;
        const storeCount = storeDefinitions.length;

        // 最終更新日時（全アイテムから最新のものを取得）
        let latestUpdate: string | null = null;
        for (const item of items) {
            for (const store of item.stores) {
                if (store.last_updated) {
                    if (!latestUpdate || store.last_updated > latestUpdate) {
                        latestUpdate = store.last_updated;
                    }
                }
            }
        }

        return {
            itemCount,
            storeCount,
            lastUpdated: latestUpdate,
        };
    }, [items, storeDefinitions]);

    const lastUpdatedText = useMemo(() => {
        if (!stats.lastUpdated) return "---";
        const diff = dayjs().diff(dayjs(stats.lastUpdated), "minute");
        if (diff < 1) return "たった今";
        if (diff < 60) return `${diff}分前`;
        const hours = Math.floor(diff / 60);
        if (hours < 24) return `${hours}時間前`;
        return dayjs(stats.lastUpdated).format("M/D HH:mm");
    }, [stats.lastUpdated]);

    const features = [
        {
            icon: BuildingStorefrontIcon,
            title: "複数ストア監視",
            description: "Amazon, ヨドバシ, 楽天など主要ECサイトを一括監視",
        },
        {
            icon: ChartBarIcon,
            title: "価格グラフ",
            description: "価格推移をグラフで確認、最安値タイミングを把握",
        },
        {
            icon: BellAlertIcon,
            title: "Slack通知",
            description: "値下げ・在庫復活をリアルタイムで通知",
        },
    ];

    return (
        <div className="bg-gradient-to-b from-gray-50 to-blue-50 rounded-xl border border-gray-200 p-6 mb-6">
            {/* タイトルと説明 */}
            <div className="text-center mb-6">
                <h2 className="text-xl font-bold text-gray-900 mb-2">
                    欲しい商品を最安値で手に入れよう
                </h2>
                <p className="text-sm text-gray-600">
                    複数のオンラインショップの価格を自動監視して、お得なタイミングをお知らせします
                </p>
            </div>

            {/* 検索ボックス（モバイル対応） */}
            <div className="flex justify-center mb-6">
                <div className="w-full max-w-md">
                    <SearchBox items={items} onItemClick={onItemClick} />
                </div>
            </div>

            {/* 統計情報 */}
            <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">{stats.itemCount}</div>
                    <div className="text-xs text-gray-500">監視アイテム</div>
                </div>
                <div className="text-center">
                    <div className="text-2xl font-bold text-blue-600">{stats.storeCount}</div>
                    <div className="text-xs text-gray-500">対応ストア</div>
                </div>
                <div className="text-center">
                    <div className="flex items-center justify-center gap-1">
                        <ClockIcon className="h-5 w-5 text-blue-600" />
                        <span className="text-sm font-semibold text-blue-600">{lastUpdatedText}</span>
                    </div>
                    <div className="text-xs text-gray-500">最終更新</div>
                </div>
            </div>

            {/* 特徴リスト */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {features.map((feature) => (
                    <div
                        key={feature.title}
                        className="flex items-start gap-3 p-3 bg-white/50 rounded-lg"
                    >
                        <feature.icon className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                        <div>
                            <div className="text-sm font-medium text-gray-900">{feature.title}</div>
                            <div className="text-xs text-gray-500">{feature.description}</div>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
