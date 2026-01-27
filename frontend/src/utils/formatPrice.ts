/**
 * 価格フォーマット用ユーティリティ関数
 */

/**
 * 価格を通貨単位付きでフォーマットする
 *
 * @param price - 価格（整数）
 * @param priceUnit - 通貨単位（例: "円", "ドル"）
 * @returns フォーマットされた価格文字列（例: "599.00ドル", "12,800円"）
 */
export function formatPrice(price: number, priceUnit: string): string {
    if (priceUnit === "円") {
        // 円の場合は整数表示
        return `${price.toLocaleString()}円`;
    }
    // 円以外の場合は小数点以下2桁表示
    return `${price.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}${priceUnit}`;
}

/**
 * 価格差分を通貨単位付きでフォーマットする（+付き）
 *
 * @param diff - 価格差分（整数）
 * @param priceUnit - 通貨単位
 * @returns フォーマットされた価格差分文字列（例: "+10.00ドル", "+1,200円"）
 */
export function formatPriceDiff(diff: number, priceUnit: string): string {
    if (priceUnit === "円") {
        return `+${diff.toLocaleString()}円`;
    }
    return `+${diff.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}${priceUnit}`;
}

/**
 * 価格をグラフのラベル用にフォーマットする（通貨記号付き）
 *
 * @param price - 価格
 * @param priceUnit - 通貨単位
 * @returns フォーマットされた価格文字列（例: "$599.00", "¥12,800"）
 */
export function formatPriceForChart(price: number, priceUnit: string): string {
    if (priceUnit === "円") {
        return `¥${price.toLocaleString()}`;
    }
    // ドルの場合は $ 記号を使用
    if (priceUnit === "ドル") {
        return `$${price.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    }
    // その他の通貨は価格+単位
    return `${price.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}${priceUnit}`;
}

/**
 * グラフのY軸ラベル用に価格をフォーマットする（簡潔版）
 *
 * @param price - 価格
 * @param priceUnit - 通貨単位
 * @param useCurrencySymbol - 通貨記号を使うかどうか
 * @returns フォーマットされた価格文字列
 */
export function formatPriceForYAxis(
    price: number,
    priceUnit: string,
    useCurrencySymbol: boolean = true
): string {
    if (priceUnit === "円") {
        return useCurrencySymbol
            ? `¥${Math.round(price).toLocaleString()}`
            : Math.round(price).toLocaleString();
    }
    if (priceUnit === "ドル") {
        return useCurrencySymbol
            ? `$${price.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
              })}`
            : price.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
              });
    }
    return `${price.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}${priceUnit}`;
}

/**
 * 通貨単位からグラフ表示用の通貨記号を取得する
 *
 * @param priceUnit - 通貨単位
 * @returns 通貨記号（例: "¥", "$"）
 */
export function getCurrencySymbol(priceUnit: string): string {
    switch (priceUnit) {
        case "円":
            return "¥";
        case "ドル":
            return "$";
        case "ユーロ":
            return "€";
        case "ポンド":
            return "£";
        default:
            return "";
    }
}
