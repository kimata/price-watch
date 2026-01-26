import { useState, useEffect, useRef, useCallback } from "react";

interface UptimeHeatmapProps {
    days: number;
    refreshKey: number;
}

interface TooltipState {
    visible: boolean;
    text: string;
    x: number;
    y: number;
}

interface HighlightState {
    visible: boolean;
    x: number;
    y: number;
    width: number;
    height: number;
}

export default function UptimeHeatmap({ days, refreshKey }: UptimeHeatmapProps) {
    const [initialLoading, setInitialLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [svgContent, setSvgContent] = useState<string>("");
    const [tooltip, setTooltip] = useState<TooltipState>({
        visible: false,
        text: "",
        x: 0,
        y: 0,
    });
    const [highlight, setHighlight] = useState<HighlightState>({
        visible: false,
        x: 0,
        y: 0,
        width: 0,
        height: 0,
    });
    const [selectedTooltipText, setSelectedTooltipText] = useState<string | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        setError(null);

        const url = `/price/api/metrics/heatmap.svg?days=${days}&_t=${Date.now()}`;

        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Failed to load heatmap");
                }
                return response.text();
            })
            .then((svg) => {
                setSvgContent(svg);
                setInitialLoading(false);
            })
            .catch(() => {
                setError("ヒートマップの読み込みに失敗しました");
                setInitialLoading(false);
            });
    }, [days, refreshKey]);

    // ツールチップとハイライトを非表示にする関数
    const hideTooltip = useCallback(() => {
        setTooltip((prev) => ({ ...prev, visible: false }));
        setHighlight((prev) => ({ ...prev, visible: false }));
        setSelectedTooltipText(null);
    }, []);

    // ヒートマップ内のクリックハンドラ
    useEffect(() => {
        if (!containerRef.current || !svgContent) return;

        const handleClick = (e: MouseEvent) => {
            e.stopPropagation();
            const target = e.target as SVGRectElement;

            if (target.classList.contains("heatmap-cell")) {
                const tooltipText = target.getAttribute("data-tooltip");
                if (tooltipText) {
                    const containerRect = containerRef.current!.getBoundingClientRect();
                    const svgElement = containerRef.current!.querySelector("svg");

                    if (!svgElement) return;

                    // SVGの実際のサイズとviewBoxの比率を計算
                    const svgRect = svgElement.getBoundingClientRect();
                    const viewBox = svgElement.viewBox.baseVal;
                    const scaleX = svgRect.width / viewBox.width;
                    const scaleY = svgRect.height / viewBox.height;

                    // セルの位置とサイズを取得
                    const cellX = parseFloat(target.getAttribute("x") || "0");
                    const cellY = parseFloat(target.getAttribute("y") || "0");
                    const cellWidth = parseFloat(target.getAttribute("width") || "0");
                    const cellHeight = parseFloat(target.getAttribute("height") || "0");

                    // スケールを適用してピクセル座標に変換
                    const highlightX = cellX * scaleX;
                    const highlightY = cellY * scaleY;
                    const highlightWidth = cellWidth * scaleX;
                    const highlightHeight = cellHeight * scaleY;

                    if (selectedTooltipText === tooltipText) {
                        // 同じセルをクリックした場合はトグル
                        hideTooltip();
                    } else {
                        // 新しいセルを選択
                        setSelectedTooltipText(tooltipText);
                        setHighlight({
                            visible: true,
                            x: highlightX,
                            y: highlightY,
                            width: highlightWidth,
                            height: highlightHeight,
                        });
                        setTooltip({
                            visible: true,
                            text: tooltipText,
                            x: e.clientX - containerRect.left,
                            y: e.clientY - containerRect.top - 30,
                        });
                    }
                }
            } else {
                // セル以外をクリックしたら非表示
                hideTooltip();
            }
        };

        const container = containerRef.current;
        container.addEventListener("click", handleClick);

        return () => {
            container.removeEventListener("click", handleClick);
        };
    }, [svgContent, selectedTooltipText, hideTooltip]);

    // ドキュメント全体のクリックでツールチップを非表示
    useEffect(() => {
        const handleDocumentClick = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                hideTooltip();
            }
        };

        document.addEventListener("click", handleDocumentClick);
        return () => {
            document.removeEventListener("click", handleDocumentClick);
        };
    }, [hideTooltip]);

    if (error && !svgContent) {
        return (
            <div className="bg-white rounded-lg shadow p-4">
                <p className="text-red-500 text-center">{error}</p>
            </div>
        );
    }

    return (
        <div className="bg-white rounded-lg shadow p-4 relative">
            {initialLoading && !svgContent && (
                <div className="animate-pulse">
                    <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
                    <div className="h-48 bg-gray-200 rounded"></div>
                </div>
            )}
            {svgContent && (
                <div ref={containerRef} className="w-full relative">
                    <div dangerouslySetInnerHTML={{ __html: svgContent }} />
                    {highlight.visible && (
                        <div
                            className="absolute pointer-events-none"
                            style={{
                                left: highlight.x,
                                top: highlight.y,
                                width: highlight.width,
                                height: highlight.height,
                                outline: "2px solid #ff6b00",
                                outlineOffset: "0px",
                                boxShadow: "0 0 6px rgba(255, 107, 0, 0.8)",
                            }}
                        />
                    )}
                </div>
            )}
            {tooltip.visible && (
                <div
                    className="absolute bg-gray-800 text-white text-sm px-2 py-1 rounded shadow-lg pointer-events-none z-10"
                    style={{
                        left: tooltip.x,
                        top: tooltip.y,
                        transform: "translateX(-50%)",
                    }}
                >
                    {tooltip.text}
                </div>
            )}
        </div>
    );
}
