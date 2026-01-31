import { createContext, useContext, useState, useCallback } from "react";
import Toast, { ToastType } from "../components/Toast";

interface ToastContextType {
    showToast: (message: string, type?: ToastType) => void;
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
    const [toastType, setToastType] = useState<ToastType>("success");
    const [toastVisible, setToastVisible] = useState(false);

    const showToast = useCallback((message: string, type: ToastType = "success") => {
        setToastMessage(message);
        setToastType(type);
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
                type={toastType}
            />
        </ToastContext.Provider>
    );
}
