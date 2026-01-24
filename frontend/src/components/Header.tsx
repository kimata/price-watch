import { CurrencyYenIcon } from "@heroicons/react/24/outline";

export default function Header() {
    return (
        <header className="bg-white shadow-sm border-b border-gray-200">
            <div className="max-w-7xl mx-auto px-4 py-4">
                <div className="flex items-center gap-3">
                    <CurrencyYenIcon className="h-8 w-8 text-blue-600" />
                    <h1 className="text-2xl font-bold text-gray-900">Price Watch</h1>
                </div>
            </div>
        </header>
    );
}
