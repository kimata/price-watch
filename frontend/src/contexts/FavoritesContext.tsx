import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";

const STORAGE_KEY = "price-watch-favorites";

interface FavoritesContextType {
    favorites: string[];
    isFavorite: (itemName: string) => boolean;
    toggleFavorite: (itemName: string) => void;
}

const FavoritesContext = createContext<FavoritesContextType | null>(null);

// localStorageからお気に入りを読み込む
function loadFavorites(): string[] {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored) {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed)) {
                return parsed;
            }
        }
    } catch {
        // パースエラーの場合は空配列を返す
    }
    return [];
}

// localStorageにお気に入りを保存
function saveFavorites(favorites: string[]): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites));
    } catch {
        // 保存に失敗しても続行
    }
}

interface FavoritesProviderProps {
    children: ReactNode;
}

export function FavoritesProvider({ children }: FavoritesProviderProps) {
    const [favorites, setFavorites] = useState<string[]>(() => loadFavorites());

    // favoritesが変更されたらlocalStorageに保存
    useEffect(() => {
        saveFavorites(favorites);
    }, [favorites]);

    const isFavorite = useCallback(
        (itemName: string): boolean => {
            return favorites.includes(itemName);
        },
        [favorites]
    );

    const toggleFavorite = useCallback((itemName: string): void => {
        setFavorites((prev) => {
            if (prev.includes(itemName)) {
                return prev.filter((name) => name !== itemName);
            }
            return [...prev, itemName];
        });
    }, []);

    return (
        <FavoritesContext.Provider value={{ favorites, isFavorite, toggleFavorite }}>
            {children}
        </FavoritesContext.Provider>
    );
}

export function useFavorites(): FavoritesContextType {
    const context = useContext(FavoritesContext);
    if (!context) {
        throw new Error("useFavorites must be used within a FavoritesProvider");
    }
    return context;
}
