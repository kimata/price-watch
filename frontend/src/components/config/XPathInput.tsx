import { useState, useEffect, useCallback } from "react";
import { CheckCircleIcon, ExclamationCircleIcon } from "@heroicons/react/24/outline";

interface XPathInputProps {
    label: string;
    value: string;
    onChange: (value: string) => void;
    placeholder?: string;
    required?: boolean;
}

// XPath の構文チェック（クライアント側）
function validateXPath(xpath: string): { valid: boolean; error: string | null } {
    if (!xpath.trim()) {
        return { valid: true, error: null }; // 空は許容
    }

    try {
        // document.evaluate を使用して構文チェック
        document.evaluate(xpath, document, null, XPathResult.ANY_TYPE, null);
        return { valid: true, error: null };
    } catch (e) {
        if (e instanceof Error) {
            // エラーメッセージを簡略化
            const message = e.message.replace(/^[^:]+: /, "");
            return { valid: false, error: message };
        }
        return { valid: false, error: "無効な XPath 式です" };
    }
}

export default function XPathInput({
    label,
    value,
    onChange,
    placeholder,
    required = false,
}: XPathInputProps) {
    const [validation, setValidation] = useState<{ valid: boolean; error: string | null }>({
        valid: true,
        error: null,
    });
    const [touched, setTouched] = useState(false);

    // デバウンスされたバリデーション
    useEffect(() => {
        const timer = setTimeout(() => {
            if (touched || value) {
                setValidation(validateXPath(value));
            }
        }, 300);
        return () => clearTimeout(timer);
    }, [value, touched]);

    const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        onChange(e.target.value);
    }, [onChange]);

    const handleBlur = useCallback(() => {
        setTouched(true);
    }, []);

    const showValidation = touched || value.length > 0;
    const showError = showValidation && !validation.valid;
    const showSuccess = showValidation && validation.valid && value.length > 0;

    return (
        <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
                {label}
                {required && <span className="text-red-500 ml-1">*</span>}
            </label>
            <div className="relative">
                <input
                    type="text"
                    value={value}
                    onChange={handleChange}
                    onBlur={handleBlur}
                    placeholder={placeholder}
                    className={`w-full px-3 py-2 pr-10 border rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm ${
                        showError
                            ? "border-red-300 bg-red-50"
                            : showSuccess
                            ? "border-green-300 bg-green-50"
                            : "border-gray-300"
                    }`}
                />
                {showSuccess && (
                    <CheckCircleIcon className="absolute right-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-green-500" />
                )}
                {showError && (
                    <ExclamationCircleIcon className="absolute right-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-red-500" />
                )}
            </div>
            {showError && validation.error && (
                <p className="mt-1 text-sm text-red-600">{validation.error}</p>
            )}
        </div>
    );
}
