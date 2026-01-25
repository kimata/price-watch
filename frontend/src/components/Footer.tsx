import { InformationCircleIcon } from "@heroicons/react/24/outline";
import type { StoreDefinition } from "../types";

interface FooterProps {
    storeDefinitions: StoreDefinition[];
}

export default function Footer({ storeDefinitions }: FooterProps) {
    // ポイント還元率が設定されているストアのみ表示
    const storesWithPointRate = storeDefinitions.filter((store) => store.point_rate > 0);

    if (storesWithPointRate.length === 0) {
        return null;
    }

    return (
        <footer className="mt-8 pb-8">
            <div className="max-w-7xl mx-auto px-4">
                <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
                    <div className="flex items-start gap-2">
                        <InformationCircleIcon className="h-5 w-5 text-gray-500 flex-shrink-0 mt-0.5" />
                        <div className="space-y-3">
                            <div>
                                <h3 className="text-sm font-medium text-gray-700 mb-1">実質価格について</h3>
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
            </div>
        </footer>
    );
}
