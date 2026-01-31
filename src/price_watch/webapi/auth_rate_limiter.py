"""認証レート制限.

IPベースのブルートフォース攻撃対策を提供します。
過去10分間に5回認証失敗したIPは3時間ロックアウトされます。
また、1時間に5回失敗するごとにSlack通知を送信できます。
"""

import threading
from dataclasses import dataclass, field

import my_lib.time

# 設定値（ロックアウト用）
FAILURE_WINDOW_SEC = 10 * 60  # 10分間
MAX_FAILURES = 5  # 最大失敗回数
LOCKOUT_DURATION_SEC = 3 * 60 * 60  # 3時間

# 設定値（Slack通知用）
NOTIFY_WINDOW_SEC = 60 * 60  # 1時間
NOTIFY_THRESHOLD = 5  # 通知閾値（5回ごとに通知）


@dataclass
class _RateLimitState:
    """レート制限の状態（スレッドセーフ）."""

    # IP -> 失敗タイムスタンプのリスト（ロックアウト用：10分ウィンドウ）
    failures: dict[str, list[float]] = field(default_factory=dict)
    # IP -> ロックアウト終了時刻
    lockouts: dict[str, float] = field(default_factory=dict)
    # IP -> 失敗タイムスタンプのリスト（通知用：1時間ウィンドウ）
    notify_failures: dict[str, list[float]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)


_state = _RateLimitState()


def is_locked_out(ip: str) -> bool:
    """指定IPがロックアウト中かどうかを確認.

    Args:
        ip: クライアントIPアドレス

    Returns:
        ロックアウト中の場合True
    """
    with _state.lock:
        lockout_until = _state.lockouts.get(ip)
        if lockout_until is None:
            return False

        now = my_lib.time.now().timestamp()
        if now < lockout_until:
            return True

        # ロックアウト期限切れ - クリーンアップ
        del _state.lockouts[ip]
        return False


def record_failure(ip: str) -> bool:
    """認証失敗を記録し、ロックアウトが発生したかを返す.

    Args:
        ip: クライアントIPアドレス

    Returns:
        この失敗によりロックアウトが発生した場合True
    """
    now = my_lib.time.now().timestamp()

    with _state.lock:
        # 既にロックアウト中なら何もしない
        if ip in _state.lockouts and now < _state.lockouts[ip]:
            return False

        # 失敗履歴を取得（なければ作成）
        if ip not in _state.failures:
            _state.failures[ip] = []

        failures = _state.failures[ip]

        # 古いエントリを削除（過去10分以内のみ保持）
        cutoff = now - FAILURE_WINDOW_SEC
        _state.failures[ip] = [t for t in failures if t > cutoff]

        # 新しい失敗を記録
        _state.failures[ip].append(now)

        # 失敗回数をチェック
        if len(_state.failures[ip]) >= MAX_FAILURES:
            # ロックアウト発動
            _state.lockouts[ip] = now + LOCKOUT_DURATION_SEC
            # 失敗履歴をクリア
            del _state.failures[ip]
            return True

        return False


def get_lockout_remaining_sec(ip: str) -> int:
    """ロックアウト残り時間を秒で取得.

    Args:
        ip: クライアントIPアドレス

    Returns:
        残り秒数（ロックアウトされていない場合は0）
    """
    with _state.lock:
        lockout_until = _state.lockouts.get(ip)
        if lockout_until is None:
            return 0

        now = my_lib.time.now().timestamp()
        remaining = lockout_until - now
        return max(0, int(remaining))


def record_failure_for_notify(ip: str) -> int | None:
    """認証失敗を記録し、5回ごとに到達した場合は失敗回数を返す.

    1時間ウィンドウで失敗をカウントし、5回、10回、15回...と
    5の倍数に達した場合にその回数を返します。

    Args:
        ip: クライアントIPアドレス

    Returns:
        5の倍数に達した場合はその回数（5, 10, 15...）、それ以外は None
    """
    now = my_lib.time.now().timestamp()

    with _state.lock:
        # 失敗履歴を取得（なければ作成）
        if ip not in _state.notify_failures:
            _state.notify_failures[ip] = []

        failures = _state.notify_failures[ip]

        # 古いエントリを削除（過去1時間以内のみ保持）
        cutoff = now - NOTIFY_WINDOW_SEC
        _state.notify_failures[ip] = [t for t in failures if t > cutoff]

        # 新しい失敗を記録
        _state.notify_failures[ip].append(now)

        # 5の倍数に達したかチェック
        count = len(_state.notify_failures[ip])
        if count > 0 and count % NOTIFY_THRESHOLD == 0:
            return count

        return None


def get_hourly_failure_count(ip: str) -> int:
    """1時間以内の失敗回数を取得.

    Args:
        ip: クライアントIPアドレス

    Returns:
        過去1時間以内の失敗回数
    """
    now = my_lib.time.now().timestamp()

    with _state.lock:
        failures = _state.notify_failures.get(ip, [])
        cutoff = now - NOTIFY_WINDOW_SEC
        return len([t for t in failures if t > cutoff])


def clear_state() -> None:
    """全状態をクリア（テスト用）."""
    with _state.lock:
        _state.failures.clear()
        _state.lockouts.clear()
        _state.notify_failures.clear()
