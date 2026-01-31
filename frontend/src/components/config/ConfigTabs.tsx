import { BuildingStorefrontIcon, TagIcon, CubeIcon } from "@heroicons/react/24/outline";

type TabType = "stores" | "categories" | "items";

interface Tab {
    id: TabType;
    label: string;
    icon: React.ComponentType<{ className?: string }>;
}

const TABS: Tab[] = [
    { id: "items", label: "アイテム", icon: CubeIcon },
    { id: "categories", label: "カテゴリ", icon: TagIcon },
    { id: "stores", label: "ストア", icon: BuildingStorefrontIcon },
];

interface ConfigTabsProps {
    activeTab: TabType;
    onChange: (tab: TabType) => void;
}

export default function ConfigTabs({ activeTab, onChange }: ConfigTabsProps) {
    return (
        <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
                {TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => onChange(tab.id)}
                            className={`
                                group inline-flex items-center py-3 px-1 border-b-2 font-medium text-sm
                                ${isActive
                                    ? "border-blue-500 text-blue-600"
                                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                                }
                            `}
                        >
                            <Icon
                                className={`
                                    -ml-0.5 mr-2 h-5 w-5
                                    ${isActive ? "text-blue-500" : "text-gray-400 group-hover:text-gray-500"}
                                `}
                            />
                            {tab.label}
                        </button>
                    );
                })}
            </nav>
        </div>
    );
}
