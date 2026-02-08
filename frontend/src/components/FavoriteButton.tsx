import { memo, useCallback, type MouseEvent } from "react";
import { HeartIcon as HeartOutline } from "@heroicons/react/24/outline";
import { HeartIcon as HeartSolid } from "@heroicons/react/24/solid";
import { useFavorites } from "../contexts/FavoritesContext";

interface FavoriteButtonProps {
    itemName: string;
    size?: "sm" | "md" | "lg";
    className?: string;
}

const SIZE_MAP = {
    sm: "h-4 w-4",
    md: "h-5 w-5",
    lg: "h-6 w-6",
};

const BUTTON_SIZE_MAP = {
    sm: "p-1",
    md: "p-1.5",
    lg: "p-2",
};

function FavoriteButton({ itemName, size = "md", className = "" }: FavoriteButtonProps) {
    const { isFavorite, toggleFavorite } = useFavorites();
    const favorited = isFavorite(itemName);

    const handleClick = useCallback(
        (e: MouseEvent) => {
            e.stopPropagation(); // カードクリック伝播を防止
            e.preventDefault();
            toggleFavorite(itemName);
        },
        [itemName, toggleFavorite]
    );

    const iconClass = SIZE_MAP[size];
    const buttonClass = BUTTON_SIZE_MAP[size];

    return (
        <button
            type="button"
            onClick={handleClick}
            className={`${buttonClass} rounded-full transition-colors cursor-pointer ${
                favorited
                    ? "text-red-500 hover:text-red-600 hover:bg-red-50"
                    : "text-gray-400 hover:text-red-400 hover:bg-gray-100"
            } ${className}`}
            title={favorited ? "お気に入りから削除" : "お気に入りに追加"}
            aria-label={favorited ? "お気に入りから削除" : "お気に入りに追加"}
        >
            {favorited ? (
                <HeartSolid className={iconClass} />
            ) : (
                <HeartOutline className={iconClass} />
            )}
        </button>
    );
}

export default memo(FavoriteButton);
