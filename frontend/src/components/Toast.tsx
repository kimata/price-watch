import { useEffect } from "react";
import { CheckCircleIcon, XMarkIcon } from "@heroicons/react/24/outline";

interface ToastProps {
    message: string;
    visible: boolean;
    onClose: () => void;
    duration?: number;
}

/**
 * 右上に表示されるトースト通知
 */
export default function Toast({ message, visible, onClose, duration = 2000 }: ToastProps) {
    useEffect(() => {
        if (visible) {
            const timer = setTimeout(() => {
                onClose();
            }, duration);
            return () => clearTimeout(timer);
        }
    }, [visible, duration, onClose]);

    if (!visible) return null;

    return (
        <div className="fixed top-4 right-4 z-50 animate-slide-in">
            <div className="flex items-center gap-2 px-4 py-3 bg-gray-800 text-white rounded-lg shadow-lg">
                <CheckCircleIcon className="h-5 w-5 text-green-400" />
                <span className="text-sm font-medium">{message}</span>
                <button
                    onClick={onClose}
                    className="ml-2 p-1 hover:bg-gray-700 rounded transition-colors"
                    aria-label="閉じる"
                >
                    <XMarkIcon className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}
