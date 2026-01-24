import { InformationCircleIcon } from "@heroicons/react/24/outline";
import type { StoreDefinition } from "../types";

interface FooterProps {
    storeDefinitions: StoreDefinition[];
}

export default function Footer({ storeDefinitions }: FooterProps) {
    // ポイント還元があるストアのみフィルタ
    const storesWithPoints = storeDefinitions.filter((s) => s.point_rate > 0);

    if (storesWithPoints.length === 0) {
        return null;
    }

    return (
        <footer className="mt-8 pb-8">
            <div className="max-w-7xl mx-auto px-4">
                <div className="bg-gray-50 rounded-lg border border-gray-200 p-4">
                    <div className="flex items-start gap-2">
                        <InformationCircleIcon className="h-5 w-5 text-gray-500 flex-shrink-0 mt-0.5" />
                        <div>
                            <h3 className="text-sm font-medium text-gray-700 mb-2">ポイント還元について</h3>
                            <ul className="space-y-1">
                                {storesWithPoints.map((store) => (
                                    <li key={store.name} className="text-xs text-gray-600">
                                        <span className="font-medium">{store.name}</span> は{" "}
                                        <span className="font-medium">{store.point_rate}%</span>{" "}
                                        のポイント還元を仮定して実質価格を計算しています。
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </footer>
    );
}
