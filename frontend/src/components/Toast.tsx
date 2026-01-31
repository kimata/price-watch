import { useEffect } from "react";
import {
    CheckCircleIcon,
    XMarkIcon,
    ExclamationCircleIcon,
    InformationCircleIcon,
} from "@heroicons/react/24/outline";

export type ToastType = "success" | "error" | "info";

interface ToastProps {
    message: string;
    visible: boolean;
    onClose: () => void;
    duration?: number;
    type?: ToastType;
}

const typeStyles: Record<ToastType, { bg: string; icon: string; Icon: typeof CheckCircleIcon }> = {
    success: {
        bg: "bg-gray-800",
        icon: "text-green-400",
        Icon: CheckCircleIcon,
    },
    error: {
        bg: "bg-red-700",
        icon: "text-red-200",
        Icon: ExclamationCircleIcon,
    },
    info: {
        bg: "bg-blue-700",
        icon: "text-blue-200",
        Icon: InformationCircleIcon,
    },
};

/**
 * 右上に表示されるトースト通知
 */
export default function Toast({
    message,
    visible,
    onClose,
    duration = 3000,
    type = "success",
}: ToastProps) {
    useEffect(() => {
        if (visible) {
            const timer = setTimeout(() => {
                onClose();
            }, duration);
            return () => clearTimeout(timer);
        }
    }, [visible, duration, onClose]);

    if (!visible) return null;

    const { bg, icon, Icon } = typeStyles[type];

    return (
        <div className="fixed top-4 right-4 z-50 animate-slide-in">
            <div className={`flex items-center gap-2 px-4 py-3 ${bg} text-white rounded-lg shadow-lg`}>
                <Icon className={`h-5 w-5 ${icon}`} />
                <span className="text-sm font-medium">{message}</span>
                <button
                    onClick={onClose}
                    className="ml-2 p-1 hover:bg-black/20 rounded transition-colors"
                    aria-label="閉じる"
                >
                    <XMarkIcon className="h-4 w-4" />
                </button>
            </div>
        </div>
    );
}
