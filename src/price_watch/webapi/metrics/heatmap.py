#!/usr/bin/env python3
"""ヒートマップ SVG 生成.

GitHub スタイルの稼働率ヒートマップを SVG で生成します。
"""

from datetime import datetime as dt

import price_watch.metrics


def generate_heatmap_svg(heatmap: price_watch.metrics.HeatmapData) -> bytes:
    """GitHubスタイルのヒートマップSVGを直接生成.

    横幅を固定し、日数に応じてセル幅を自動調整。縦は24時間固定。

    Args:
        heatmap: ヒートマップデータ

    Returns:
        SVG データ（バイト列）
    """
    dates = heatmap.dates
    hours = heatmap.hours
    day_names = ["月", "火", "水", "木", "金", "土", "日"]

    # カラーパレット（5段階：灰色→黄色→緑）
    colors = ["#e0e0e0", "#fff59d", "#ffee58", "#a5d610", "#4caf50"]

    def get_color(ratio: float | None) -> str:
        """稼働率から色を取得."""
        if ratio is None:
            return "#ebedf0"
        if ratio < 0.2:
            return colors[0]
        elif ratio < 0.4:
            return colors[1]
        elif ratio < 0.6:
            return colors[2]
        elif ratio < 0.8:
            return colors[3]
        else:
            return colors[4]

    # 固定横幅とマージン
    target_width = 1000.0  # px
    margin_left = 25.0  # 時間ラベル用
    margin_right = 4.0
    margin_top = 18.0  # 日付ラベル用
    margin_bottom = 10.0  # 24時ラベル用
    cell_gap = 1.0  # px

    # 縦方向は固定（24時間）
    cell_height = 6.0  # px
    cell_step_y = cell_height + cell_gap

    if not dates:
        return (
            b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 30" '
            b'width="100%" preserveAspectRatio="xMidYMid meet">'
            b'<text x="500" y="20" text-anchor="middle" font-size="12">No data</text></svg>'
        )

    num_dates = len(dates)
    num_hours = len(hours)

    # セルデータをマップ化
    cell_map = {(c.date, c.hour): c.uptime_rate for c in heatmap.cells}

    # セル幅を計算（横幅固定）
    available_width = target_width - margin_left - margin_right
    cell_step_x = available_width / num_dates
    cell_width = max(1, cell_step_x - cell_gap)

    # SVGサイズ計算
    svg_width = target_width
    svg_height = margin_top + num_hours * cell_step_y + margin_bottom

    # SVG構築開始（viewBoxでレスポンシブ対応）
    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_width} {svg_height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet">',
        "<style>",
        "  .label { font-family: sans-serif; font-size: 11px; fill: #57606a; }",
        "  .label-sat { font-family: sans-serif; font-size: 11px; fill: #2196f3; }",
        "  .label-sun { font-family: sans-serif; font-size: 11px; fill: #cf222e; }",
        "  .heatmap-cell { cursor: pointer; }",
        "  .heatmap-cell.selected { stroke: #ff6b00; stroke-width: 2; }",
        "</style>",
    ]

    # 日付ラベル（間引いて表示）
    label_width_estimate = 85  # "1月23日(水)" の推定幅
    label_step = max(1, int(label_width_estimate / cell_step_x) + 1)

    # 表示するラベルのインデックスを収集
    label_indices = [j for j in range(num_dates) if j % label_step == 0]

    label_half_width = label_width_estimate / 2  # ラベル幅の半分
    # 許容される最小x座標（左端から少し余裕を持たせつつ、時刻ラベルエリアも活用）
    min_label_x = 4.0

    for j in label_indices:
        date_str = dates[j]
        date_obj = dt.strptime(date_str, "%Y-%m-%d")
        dow = day_names[date_obj.weekday()]
        label = f"{date_obj.month}月{date_obj.day}日({dow})"

        # 位置とアンカーを決定
        cell_center_x = margin_left + j * cell_step_x + cell_width / 2

        if j == label_indices[0] and cell_center_x - label_half_width < min_label_x:
            # 最初のラベル: 見切れる場合のみ左寄せ（時刻ラベルエリアも活用）
            x = min_label_x
            anchor = "start"
        elif j == label_indices[-1] and cell_center_x + label_half_width > svg_width:
            # 最後のラベル: 見切れる場合のみ右寄せ
            x = margin_left + j * cell_step_x + cell_width
            anchor = "end"
        else:
            # 中央揃え
            x = cell_center_x
            anchor = "middle"

        weekday = date_obj.weekday()
        if weekday == 5:  # 土曜日
            css_class = "label-sat"
        elif weekday == 6:  # 日曜日
            css_class = "label-sun"
        else:
            css_class = "label"
        svg_parts.append(
            f'<text x="{x}" y="{margin_top - 5}" class="{css_class}" text-anchor="{anchor}">{label}</text>'
        )

    # 時間ラベル（左側: 0, 6, 12, 18, 24）
    time_labels = [0, 6, 12, 18, 24]
    for hour_label in time_labels:
        if hour_label == 24:
            # 24時は最下部（23時台セルの下端）
            y = margin_top + (num_hours - 1) * cell_step_y + cell_height
        else:
            # 各時間の行のセンターに配置
            y = margin_top + hour_label * cell_step_y + cell_height / 2
        svg_parts.append(
            f'<text x="{margin_left - 4}" y="{y}" class="label" text-anchor="end" '
            f'dominant-baseline="middle">{hour_label}</text>'
        )

    # セル描画（縦:24時間、横:日付）
    for i, hour in enumerate(hours):
        y = margin_top + i * cell_step_y
        for j, date_str in enumerate(dates):
            x = margin_left + j * cell_step_x
            ratio = cell_map.get((date_str, hour))
            color = get_color(ratio)
            # ツールチップ用のテキスト
            date_obj = dt.strptime(date_str, "%Y-%m-%d")
            dow = day_names[date_obj.weekday()]
            ratio_text = f"{ratio * 100:.1f}%" if ratio is not None else "データなし"
            tooltip = f"{date_obj.month}月{date_obj.day}日({dow}) {hour}時台: {ratio_text}"
            svg_parts.append(
                f'<rect x="{x}" y="{y}" width="{cell_width}" height="{cell_height}" '
                f'fill="{color}" data-tooltip="{tooltip}" class="heatmap-cell" '
                f'style="cursor: pointer;"/>'
            )

    svg_parts.append("</svg>")

    return "\n".join(svg_parts).encode("utf-8")
