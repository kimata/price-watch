import { CalendarIcon } from "@heroicons/react/24/outline";
import clsx from "clsx";
import type { Period } from "../types";
import { PERIOD_OPTIONS } from "../types";

interface PeriodSelectorProps {
    selected: Period;
    onChange: (period: Period) => void;
}

export default function PeriodSelector({ selected, onChange }: PeriodSelectorProps) {
    return (
        <div className="flex items-center gap-2 flex-wrap">
            <CalendarIcon className="h-5 w-5 text-gray-500" />
            <span className="text-sm text-gray-600 mr-2">期間:</span>
            <div className="flex gap-1 flex-wrap">
                {PERIOD_OPTIONS.map((option) => (
                    <button
                        key={option.value}
                        onClick={() => onChange(option.value)}
                        className={clsx(
                            "px-3 py-1.5 text-sm rounded-md transition-colors cursor-pointer",
                            selected === option.value
                                ? "bg-blue-600 text-white"
                                : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                        )}
                    >
                        {option.label}
                    </button>
                ))}
            </div>
        </div>
    );
}
