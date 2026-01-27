/**
 * 日付フォーマットユーティリティ
 */

/**
 * YYYY-MM-DD 形式の日付を「M月D日」形式に変換
 * @param dateStr YYYY-MM-DD 形式の日付文字列
 * @returns 「1月6日」のような形式の文字列
 */
export function formatDateToJapanese(dateStr: string): string {
    const match = dateStr.match(/^\d{4}-(\d{2})-(\d{2})$/);
    if (!match) return dateStr;
    const month = parseInt(match[1], 10);
    const day = parseInt(match[2], 10);
    return `${month}月${day}日`;
}
