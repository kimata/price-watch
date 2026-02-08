import type { Item } from "../types";
import SearchBox from "./SearchBox";

interface HeaderProps {
    items?: Item[];
    onItemClick?: (item: Item) => void;
}

export default function Header({ items = [], onItemClick }: HeaderProps) {
    return (
        <header className="bg-white shadow-sm border-b border-gray-200">
            <div className="max-w-7xl mx-auto px-4 py-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <img src={`${import.meta.env.BASE_URL}logo.svg`} alt="Price Watch" className="h-9 w-9" />
                        <h1 className="text-2xl font-bold text-gray-900">Price Watch</h1>
                    </div>
                    {items.length > 0 && onItemClick && (
                        <div className="hidden sm:block">
                            <SearchBox items={items} onItemClick={onItemClick} />
                        </div>
                    )}
                </div>
            </div>
        </header>
    );
}
