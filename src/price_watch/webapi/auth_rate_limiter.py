"""認証レート制限.

IPベースのブルートフォース攻撃対策を提供します。
過去10分間に5回認証失敗したIPは3時間ロックアウトされます。
"""

import threading
from dataclasses import dataclass, field

import my_lib.time

# 設定値
FAILURE_WINDOW_SEC = 10 * 60  # 10分間
MAX_FAILURES = 5  # 最大失敗回数
LOCKOUT_DURATION_SEC = 3 * 60 * 60  # 3時間


@dataclass
class _RateLimitState:
    """レート制限の状態（スレッドセーフ）."""

    # IP -> 失敗タイムスタンプのリスト
    failures: dict[str, list[float]] = field(default_factory=dict)
    # IP -> ロックアウト終了時刻
    lockouts: dict[str, float] = field(default_factory=dict)
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


def clear_state() -> None:
    """全状態をクリア（テスト用）."""
    with _state.lock:
        _state.failures.clear()
        _state.lockouts.clear()
