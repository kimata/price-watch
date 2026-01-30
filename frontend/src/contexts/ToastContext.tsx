import { createContext, useContext, useState, useCallback } from "react";
import Toast from "../components/Toast";

interface ToastContextType {
    showToast: (message: string) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function useToast(): ToastContextType {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error("useToast must be used within a ToastProvider");
    }
    return context;
}

interface ToastProviderProps {
    children: React.ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
    const [toastMessage, setToastMessage] = useState<string | null>(null);
    const [toastVisible, setToastVisible] = useState(false);

    const showToast = useCallback((message: string) => {
        setToastMessage(message);
        setToastVisible(true);
    }, []);

    const handleClose = useCallback(() => {
        setToastVisible(false);
    }, []);

    return (
        <ToastContext.Provider value={{ showToast }}>
            {children}
            <Toast
                message={toastMessage || ""}
                visible={toastVisible}
                onClose={handleClose}
            />
        </ToastContext.Provider>
    );
}
