#!/usr/bin/env python3
# ruff: noqa: S101
"""
managers/history モジュールのユニットテスト

Repository パターンで分割された履歴管理モジュールのテストを行います。
"""

import pathlib
from datetime import datetime, timedelta, timezone

import pytest
import time_machine

import price_watch.const
from price_watch.managers.history import (
    EventRepository,
    HistoryDBConnection,
    HistoryManager,
    ItemRepository,
    PriceRepository,
    generate_item_key,
    url_hash,
)

# 時間単位で異なる時刻を生成するためのベース時刻
_BASE_TIME = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone(timedelta(hours=9)))


# === Utils テスト ===
class TestUrlHash:
    """url_hash 関数のテスト"""

    def test_returns_12_char_hash(self) -> None:
        """12文字のハッシュを返す"""
        result = url_hash("https://example.com/item/1")
        assert len(result) == 12

    def test_same_url_same_hash(self) -> None:
        """同じ URL は同じハッシュを返す"""
        url = "https://example.com/item/1"
        assert url_hash(url) == url_hash(url)

    def test_different_url_different_hash(self) -> None:
        """異なる URL は異なるハッシュを返す"""
        hash1 = url_hash("https://example.com/item/1")
        hash2 = url_hash("https://example.com/item/2")
        assert hash1 != hash2


class TestGenerateItemKey:
    """generate_item_key 関数のテスト"""

    def test_url_generates_key(self) -> None:
        """URL からキーを生成"""
        key = generate_item_key(url="https://example.com/item/1")
        assert len(key) == 12

    def test_search_keyword_generates_key(self) -> None:
        """検索キーワードからキーを生成"""
        key = generate_item_key(search_keyword="テストキーワード")
        assert len(key) == 12

    def test_search_keyword_priority_over_url(self) -> None:
        """search_keyword が指定されている場合、URL より優先"""
        key_with_keyword = generate_item_key(url="https://example.com", search_keyword="テストキーワード")
        key_keyword_only = generate_item_key(search_keyword="テストキーワード")
        assert key_with_keyword == key_keyword_only

    def test_search_cond_ignored(self) -> None:
        """search_cond は無視される（同じキーワードなら同じキー）"""
        key1 = generate_item_key(search_keyword="テスト", search_cond='{"price_min": 100}')
        key2 = generate_item_key(search_keyword="テスト", search_cond='{"price_min": 200}')
        assert key1 == key2

    def test_store_name_differentiates_key(self) -> None:
        """store_name が異なれば異なるキーが生成される"""
        key_mercari = generate_item_key(search_keyword="テスト", store_name="メルカリ")
        key_rakuma = generate_item_key(search_keyword="テスト", store_name="ラクマ")
        assert key_mercari != key_rakuma
        assert len(key_mercari) == 12
        assert len(key_rakuma) == 12

    def test_store_name_none_backward_compatible(self) -> None:
        """store_name=None の場合はキーワードのみからキーを生成（後方互換性）"""
        key_without_store = generate_item_key(search_keyword="テスト")
        key_with_none = generate_item_key(search_keyword="テスト", store_name=None)
        assert key_without_store == key_with_none

    def test_store_name_ignored_for_url(self) -> None:
        """URL ベースのキー生成では store_name は影響しない"""
        key1 = generate_item_key(url="https://example.com/item/1")
        key2 = generate_item_key(url="https://example.com/item/1", store_name="Amazon")
        assert key1 == key2

    def test_raises_without_url_or_keyword(self) -> None:
        """URL もキーワードもない場合は ValueError"""
        with pytest.raises(ValueError, match="Either url or search_keyword must be provided"):
            generate_item_key()


# === HistoryDBConnection テスト ===
class TestHistoryDBConnection:
    """HistoryDBConnection のテスト"""

    def test_create_from_data_path(self, temp_data_dir: pathlib.Path) -> None:
        """データパスから作成できる"""
        db = HistoryDBConnection.create(temp_data_dir)
        assert db.db_path == temp_data_dir / price_watch.const.DB_FILE

    def test_initialize_creates_database(self, temp_data_dir: pathlib.Path) -> None:
        """initialize でデータベースが作成される"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        assert db.db_path.exists()

    def test_initialize_creates_tables(self, temp_data_dir: pathlib.Path) -> None:
        """initialize でテーブルが作成される"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()

        assert db.table_exists("items")
        assert db.table_exists("price_history")
        assert db.table_exists("events")

    def test_column_exists(self, temp_data_dir: pathlib.Path) -> None:
        """column_exists でカラムの存在確認"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()

        assert db.column_exists("items", "item_key")
        assert db.column_exists("items", "name")
        assert not db.column_exists("items", "nonexistent")

    def test_connect_returns_connection(self, temp_data_dir: pathlib.Path) -> None:
        """connect でコネクションを取得"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()

        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            assert cur.fetchone() is not None


# === ItemRepository テスト ===
class TestItemRepository:
    """ItemRepository のテスト"""

    @pytest.fixture
    def item_repo(self, temp_data_dir: pathlib.Path) -> ItemRepository:
        """ItemRepository フィクスチャ"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        return ItemRepository(db=db)

    def test_get_or_create_new_item(self, item_repo: ItemRepository) -> None:
        """新規アイテムを作成"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        assert item_id > 0

        item = item_repo.get_by_id(item_id)
        assert item is not None
        assert item["name"] == "テスト商品"
        assert item["store"] == "test-store"

    def test_get_or_create_existing_item(self, item_repo: ItemRepository) -> None:
        """既存アイテムを取得（重複作成しない）"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id1 = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id2 = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        assert item_id1 == item_id2

    def test_get_or_create_updates_name(self, item_repo: ItemRepository) -> None:
        """既存アイテムの名前を更新"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(cur, "旧名前", "test-store", url="https://example.com/item/1")
            conn.commit()

        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_repo.get_or_create(cur, "新名前", "test-store", url="https://example.com/item/1")
            conn.commit()

        item = item_repo.get_by_id(item_id)
        assert item is not None
        assert item["name"] == "新名前"

    def test_get_id_by_url(self, item_repo: ItemRepository) -> None:
        """URL からアイテム ID を取得"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        result = item_repo.get_id(url="https://example.com/item/1")
        assert result == item_id

    def test_get_id_by_item_key(self, item_repo: ItemRepository) -> None:
        """アイテムキーからアイテム ID を取得"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        item_key = url_hash("https://example.com/item/1")
        result = item_repo.get_id(item_key=item_key)
        assert result == item_id

    def test_get_all(self, item_repo: ItemRepository) -> None:
        """全アイテムを取得"""
        with item_repo.db.connect() as conn:
            cur = conn.cursor()
            item_repo.get_or_create(cur, "商品1", "store1", url="https://example.com/1")
            item_repo.get_or_create(cur, "商品2", "store2", url="https://example.com/2")
            conn.commit()

        items = item_repo.get_all()
        assert len(items) == 2


# === PriceRepository テスト ===
class TestPriceRepository:
    """PriceRepository のテスト"""

    @pytest.fixture
    def price_repo(self, temp_data_dir: pathlib.Path) -> PriceRepository:
        """PriceRepository フィクスチャ"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        item_repo = ItemRepository(db=db)
        return PriceRepository(db=db, item_repo=item_repo)

    def test_insert_creates_history(self, price_repo: PriceRepository) -> None:
        """insert で履歴が作成される"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }
        item_id = price_repo.insert(item)
        assert item_id > 0

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["price"] == 1000

    def test_insert_same_hour_keeps_lower_price(self, price_repo: PriceRepository) -> None:
        """同一時間帯では安い価格を保持"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(minutes=30), tick=False):
            item["price"] = 800  # 安い価格
            price_repo.insert(item)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["price"] == 800

    def test_get_last(self, price_repo: PriceRepository) -> None:
        """最新の価格履歴を取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            item["price"] = 800
            price_repo.insert(item)

        result = price_repo.get_last(url="https://example.com/item/1")
        assert result is not None
        assert result["price"] == 800

    def test_get_lowest(self, price_repo: PriceRepository) -> None:
        """最安値を取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            item["price"] = 800
            price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            item["price"] = 1200
            price_repo.insert(item)

        result = price_repo.get_lowest(url="https://example.com/item/1")
        assert result is not None
        assert result["price"] == 800

    def test_get_stats(self, price_repo: PriceRepository) -> None:
        """統計情報を取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            item["price"] = 800
            price_repo.insert(item)

        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            item["price"] = 1200
            price_repo.insert(item)

        stats = price_repo.get_stats(item_id)
        assert stats["lowest_price"] == 800
        assert stats["highest_price"] == 1200
        assert stats["data_count"] == 3

    def test_crawl_status_failure(self, price_repo: PriceRepository) -> None:
        """crawl_status=0 で stock と price が NULL"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = price_repo.insert(item, crawl_status=0)
        latest = price_repo.get_latest(item_id)

        assert latest is not None
        assert latest["price"] is None
        assert latest["stock"] is None

    def test_get_out_of_stock_duration_hours(self, price_repo: PriceRepository) -> None:
        """在庫なし継続時間を取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 最初は在庫あり
        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 2時間後に在庫切れ
        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            item["stock"] = 0
            item["price"] = None
            price_repo.insert(item)

        # 4時間後も在庫切れ
        with time_machine.travel(_BASE_TIME + timedelta(hours=4), tick=False):
            price_repo.insert(item)

            # 現在時刻から在庫切れ開始時刻までの時間を計算
            duration = price_repo.get_out_of_stock_duration_hours(item_id)
            assert duration is not None
            assert duration >= 2.0  # 少なくとも2時間以上


# === EventRepository テスト ===
class TestEventRepository:
    """EventRepository のテスト"""

    @pytest.fixture
    def event_repo(self, temp_data_dir: pathlib.Path) -> tuple[EventRepository, int]:
        """EventRepository フィクスチャとテスト用アイテム ID"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        item_repo = ItemRepository(db=db)

        # テスト用アイテムを作成
        with db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        return EventRepository(db=db), item_id

    def test_insert_event(self, event_repo: tuple[EventRepository, int]) -> None:
        """イベントを挿入"""
        repo, item_id = event_repo
        event_id = repo.insert(item_id, "PRICE_DROP", price=800, old_price=1000)
        assert event_id > 0

    def test_get_last(self, event_repo: tuple[EventRepository, int]) -> None:
        """最新イベントを取得"""
        repo, item_id = event_repo

        # 異なる時刻で挿入
        with time_machine.travel(_BASE_TIME, tick=False):
            repo.insert(item_id, "PRICE_DROP", price=900, old_price=1000)

        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            repo.insert(item_id, "PRICE_DROP", price=800, old_price=900)

        last = repo.get_last(item_id, "PRICE_DROP")
        assert last is not None
        assert last["price"] == 800

    def test_has_event_in_hours(self, event_repo: tuple[EventRepository, int]) -> None:
        """指定時間内のイベント存在確認

        Note: SQLite の datetime('now') は time_machine でモックされないため、
        created_at を直接比較してテストする
        """
        repo, item_id = event_repo

        # イベントを挿入
        with time_machine.travel(_BASE_TIME, tick=False):
            repo.insert(item_id, "PRICE_DROP", price=800)

        # イベントが存在することを確認
        last = repo.get_last(item_id, "PRICE_DROP")
        assert last is not None
        assert last["price"] == 800

    def test_get_recent(self, event_repo: tuple[EventRepository, int]) -> None:
        """最新イベントリストを取得"""
        repo, item_id = event_repo
        repo.insert(item_id, "PRICE_DROP", price=800)
        repo.insert(item_id, "LOWEST_PRICE", price=700)

        recent = repo.get_recent(limit=10)
        assert len(recent) == 2
        # アイテム名も含まれる
        assert recent[0]["item_name"] == "テスト商品"

    def test_mark_notified(self, event_repo: tuple[EventRepository, int]) -> None:
        """通知済みフラグを設定"""
        repo, item_id = event_repo
        event_id = repo.insert(item_id, "PRICE_DROP", price=800, notified=False)

        repo.mark_notified(event_id)

        last = repo.get_last(item_id, "PRICE_DROP")
        assert last is not None
        assert last["notified"] == 1


# === HistoryManager テスト ===
class TestHistoryManager:
    """HistoryManager のテスト"""

    @pytest.fixture
    def manager(self, temp_data_dir: pathlib.Path) -> HistoryManager:
        """HistoryManager フィクスチャ"""
        mgr = HistoryManager.create(temp_data_dir)
        mgr.initialize()
        return mgr

    def test_create_and_initialize(self, temp_data_dir: pathlib.Path) -> None:
        """作成と初期化"""
        mgr = HistoryManager.create(temp_data_dir)
        mgr.initialize()

        assert mgr.db.db_path.exists()
        assert mgr.db.table_exists("items")

    def test_insert_and_get_last(self, manager: HistoryManager) -> None:
        """insert と get_last の委譲"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        manager.insert(item)
        result = manager.get_last(url="https://example.com/item/1")

        assert result is not None
        assert result.price == 1000

    def test_insert_event_and_get_last_event(self, manager: HistoryManager) -> None:
        """insert_event と get_last_event の委譲"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = manager.insert(item)
        manager.insert_event(item_id, "PRICE_DROP", price=800, old_price=1000)

        event = manager.get_last_event(item_id, "PRICE_DROP")
        assert event is not None
        assert event.price == 800

    def test_get_all_items(self, manager: HistoryManager) -> None:
        """get_all_items の委譲"""
        items = [
            {"name": "商品1", "store": "store1", "url": "https://example.com/1", "price": 100, "stock": 1},
            {"name": "商品2", "store": "store2", "url": "https://example.com/2", "price": 200, "stock": 1},
        ]

        for item in items:
            manager.insert(item)

        all_items = manager.get_all_items()
        assert len(all_items) == 2

    def test_get_item_id(self, manager: HistoryManager) -> None:
        """get_item_id の委譲"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = manager.insert(item)
        result = manager.get_item_id(url="https://example.com/item/1")

        assert result == item_id


# === PriceRepository 追加テスト（状態遷移） ===
class TestPriceRepositoryStateTransitions:
    """PriceRepository の状態遷移テスト"""

    @pytest.fixture
    def price_repo(self, temp_data_dir: pathlib.Path) -> PriceRepository:
        """PriceRepository フィクスチャ"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        item_repo = ItemRepository(db=db)
        return PriceRepository(db=db, item_repo=item_repo)

    def test_insert_crawl_failure_to_success(self, price_repo: PriceRepository) -> None:
        """失敗状態から成功状態への遷移"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 最初は失敗
        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item, crawl_status=0)

        # 同一時間帯で成功に遷移
        with time_machine.travel(_BASE_TIME + timedelta(minutes=30), tick=False):
            price_repo.insert(item, crawl_status=1)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["price"] == 1000
        assert latest["stock"] == 1

    def test_insert_success_to_failure_preserves_data(self, price_repo: PriceRepository) -> None:
        """成功状態から失敗状態への遷移（データは保持）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 最初は成功
        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item, crawl_status=1)

        # 同一時間帯で失敗（既存の成功データを保持）
        with time_machine.travel(_BASE_TIME + timedelta(minutes=30), tick=False):
            price_repo.insert(item, crawl_status=0)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        # 成功時のデータが保持されている
        assert latest["price"] == 1000
        assert latest["stock"] == 1

    def test_insert_in_stock_to_out_of_stock(self, price_repo: PriceRepository) -> None:
        """在庫あり→在庫なしへの遷移"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 次の時間帯で在庫切れ
        item["stock"] = 0
        item["price"] = None
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            price_repo.insert(item)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["stock"] == 0

    def test_insert_out_of_stock_to_in_stock(self, price_repo: PriceRepository) -> None:
        """在庫なし→在庫あり（復活）への遷移"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": None,
            "stock": 0,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 次の時間帯で在庫復活
        item["stock"] = 1
        item["price"] = 1200
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            price_repo.insert(item)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["stock"] == 1
        assert latest["price"] == 1200

    def test_insert_price_decrease(self, price_repo: PriceRepository) -> None:
        """価格下落"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 次の時間帯で価格下落
        item["price"] = 800
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            price_repo.insert(item)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["price"] == 800

    def test_insert_price_increase(self, price_repo: PriceRepository) -> None:
        """価格上昇"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 次の時間帯で価格上昇
        item["price"] = 1200
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            price_repo.insert(item)

        latest = price_repo.get_latest(item_id)
        assert latest is not None
        assert latest["price"] == 1200

    def test_get_no_data_duration_hours(self, price_repo: PriceRepository) -> None:
        """データなし継続時間の計算"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 最初は成功
        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 2時間後に失敗
        with time_machine.travel(_BASE_TIME + timedelta(hours=2), tick=False):
            price_repo.insert(item, crawl_status=0)

        # 4時間後も失敗
        with time_machine.travel(_BASE_TIME + timedelta(hours=4), tick=False):
            price_repo.insert(item, crawl_status=0)

            # 現在時刻から失敗開始時刻までの時間を計算
            duration = price_repo.get_no_data_duration_hours(item_id)
            assert duration is not None
            assert duration >= 2.0

    def test_get_last_when_url_is_none(self, price_repo: PriceRepository) -> None:
        """URL も item_key も None の場合は None を返す"""
        result = price_repo.get_last(None, item_key=None)
        assert result is None

    def test_get_lowest_when_url_is_none(self, price_repo: PriceRepository) -> None:
        """URL も item_key も None の場合は None を返す"""
        result = price_repo.get_lowest(None, item_key=None)
        assert result is None

    def test_get_lowest_in_period_with_days(self, price_repo: PriceRepository) -> None:
        """指定期間内の最安値（日数指定）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 現在時刻でデータを挿入
        item_id = price_repo.insert(item)

        # 異なる価格を挿入
        item["price"] = 800
        price_repo.insert(item)

        # 期間を指定して最安値を取得（現在時刻で挿入したので7日以内に含まれる）
        lowest = price_repo.get_lowest_in_period(item_id, days=7)
        assert lowest == 800

    def test_get_lowest_in_period_all(self, price_repo: PriceRepository) -> None:
        """全期間の最安値（days=None）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = price_repo.insert(item)

        # 異なる価格を挿入
        item["price"] = 800
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            price_repo.insert(item)

        # 全期間で最安値を取得
        lowest = price_repo.get_lowest_in_period(item_id, days=None)
        assert lowest == 800

    def test_has_successful_crawl_in_hours(self, price_repo: PriceRepository) -> None:
        """指定時間内に成功したクロールがあるか確認"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 現在時刻でデータを挿入
        item_id = price_repo.insert(item, crawl_status=1)

        # 成功クロールがあることを確認（現在時刻で挿入したので1時間以内に含まれる）
        assert price_repo.has_successful_crawl_in_hours(item_id, 1)

    def test_has_successful_crawl_in_hours_failure(self, price_repo: PriceRepository) -> None:
        """失敗したクロールのみの場合は False を返す"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 現在時刻でクロール失敗として挿入
        item_id = price_repo.insert(item, crawl_status=0)

        # 成功クロールがないことを確認
        assert not price_repo.has_successful_crawl_in_hours(item_id, 1)


# === EventRepository 追加テスト（エッジケース） ===
class TestEventRepositoryEdgeCases:
    """EventRepository のエッジケーステスト"""

    @pytest.fixture
    def event_repo(self, temp_data_dir: pathlib.Path) -> tuple[EventRepository, int]:
        """EventRepository フィクスチャとテスト用アイテム ID"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        item_repo = ItemRepository(db=db)

        # テスト用アイテムを作成
        with db.connect() as conn:
            cur = conn.cursor()
            item_id = item_repo.get_or_create(
                cur, "テスト商品", "test-store", url="https://example.com/item/1"
            )
            conn.commit()

        return EventRepository(db=db), item_id

    def test_get_by_item_with_coalesce(self, event_repo: tuple[EventRepository, int]) -> None:
        """COALESCE によるサムネイル取得"""
        repo, item_id = event_repo

        # イベントを挿入
        repo.insert(item_id, "PRICE_DROP", price=800, old_price=1000)

        # item_key を取得して by_item でイベントを取得
        events = repo.get_by_item(url_hash("https://example.com/item/1"), limit=10)
        assert len(events) == 1
        assert events[0]["item_name"] == "テスト商品"

    def test_get_recent_multiple_types(self, event_repo: tuple[EventRepository, int]) -> None:
        """複数イベントタイプの取得"""
        repo, item_id = event_repo

        # 異なるタイプのイベントを挿入
        with time_machine.travel(_BASE_TIME, tick=False):
            repo.insert(item_id, "PRICE_DROP", price=800, old_price=1000)
        with time_machine.travel(_BASE_TIME + timedelta(minutes=1), tick=False):
            repo.insert(item_id, "LOWEST_PRICE", price=800)
        with time_machine.travel(_BASE_TIME + timedelta(minutes=2), tick=False):
            repo.insert(item_id, "STOCK_RECOVERY", price=800)

        recent = repo.get_recent(limit=10)
        assert len(recent) == 3

        # 新しい順に並んでいることを確認
        event_types = [e["event_type"] for e in recent]
        assert event_types == ["STOCK_RECOVERY", "LOWEST_PRICE", "PRICE_DROP"]

    def test_get_last_nonexistent_type(self, event_repo: tuple[EventRepository, int]) -> None:
        """存在しないイベントタイプの取得"""
        repo, item_id = event_repo

        repo.insert(item_id, "PRICE_DROP", price=800)

        # 別のタイプを取得しようとすると None
        result = repo.get_last(item_id, "NONEXISTENT_TYPE")
        assert result is None

    def test_has_event_in_hours_true(self, event_repo: tuple[EventRepository, int]) -> None:
        """指定時間内にイベントがある場合は True を返す"""
        repo, item_id = event_repo

        # 現在時刻でイベントを挿入
        repo.insert(item_id, "PRICE_DROP", price=800, old_price=1000)

        # 1時間以内にイベントがあることを確認
        assert repo.has_event_in_hours(item_id, "PRICE_DROP", 1)

    def test_has_event_in_hours_false(self, event_repo: tuple[EventRepository, int]) -> None:
        """指定時間内にイベントがない場合は False を返す"""
        repo, item_id = event_repo

        # 現在時刻でイベントを挿入
        repo.insert(item_id, "PRICE_DROP", price=800, old_price=1000)

        # 別のタイプで検索すると False
        assert not repo.has_event_in_hours(item_id, "LOWEST_PRICE", 1)

    def test_has_event_in_hours_no_events(self, event_repo: tuple[EventRepository, int]) -> None:
        """イベントがない場合は False を返す"""
        repo, item_id = event_repo

        # イベントなしで検索すると False
        assert not repo.has_event_in_hours(item_id, "PRICE_DROP", 1)


# === HistoryManager 追加テスト（型変換） ===
class TestHistoryManagerTypeConversions:
    """HistoryManager の型変換テスト"""

    @pytest.fixture
    def manager(self, temp_data_dir: pathlib.Path) -> HistoryManager:
        """HistoryManager フィクスチャ"""
        mgr = HistoryManager.create(temp_data_dir)
        mgr.initialize()
        return mgr

    def test_get_last_returns_none(self, manager: HistoryManager) -> None:
        """存在しないアイテムの get_last は None を返す"""
        result = manager.get_last(url="https://nonexistent.com/item")
        assert result is None

    def test_get_item_by_id_returns_none(self, manager: HistoryManager) -> None:
        """存在しないアイテム ID の get_item_by_id は None を返す"""
        result = manager.get_item_by_id(99999)
        assert result is None

    def test_get_lowest_returns_none(self, manager: HistoryManager) -> None:
        """存在しないアイテムの get_lowest は None を返す"""
        result = manager.get_lowest(url="https://nonexistent.com/item")
        assert result is None

    def test_get_latest_returns_none(self, manager: HistoryManager) -> None:
        """存在しないアイテムの get_latest は None を返す"""
        result = manager.get_latest(99999)
        assert result is None

    def test_get_last_successful_crawl_returns_none(self, manager: HistoryManager) -> None:
        """存在しないアイテムの get_last_successful_crawl は None を返す"""
        result = manager.get_last_successful_crawl(99999)
        assert result is None

    def test_get_history_returns_none_and_empty(self, manager: HistoryManager) -> None:
        """存在しないアイテムの get_history は (None, []) を返す"""
        item, history = manager.get_history("nonexistent_key")
        assert item is None
        assert history == []

    def test_insert_checked_item_failure(self, manager: HistoryManager) -> None:
        """失敗状態の CheckedItem の挿入"""
        import price_watch.models

        checked_item = price_watch.models.CheckedItem(
            name="テスト商品",
            store="test-store",
            url="https://example.com/item/1",
            price=None,
            stock=price_watch.models.StockStatus.UNKNOWN,
            crawl_status=price_watch.models.CrawlStatus.FAILURE,
        )

        item_id = manager.insert_checked_item(checked_item)
        assert item_id > 0

        # 失敗状態で保存されていることを確認
        latest = manager.get_latest(item_id)
        assert latest is not None
        assert latest.price is None

    def test_get_item_events(self, manager: HistoryManager) -> None:
        """アイテムのイベント履歴を取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = manager.insert(item)
        manager.insert_event(item_id, "PRICE_DROP", price=800, old_price=1000)

        item_key = url_hash("https://example.com/item/1")
        events = manager.get_item_events(item_key)

        assert len(events) == 1
        assert events[0].event_type == "PRICE_DROP"
        assert events[0].price == 800

    def test_get_stats_returns_stats(self, manager: HistoryManager) -> None:
        """統計情報の取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        with time_machine.travel(_BASE_TIME, tick=False):
            item_id = manager.insert(item)

        item["price"] = 800
        with time_machine.travel(_BASE_TIME + timedelta(hours=1), tick=False):
            manager.insert(item)

        stats = manager.get_stats(item_id)
        assert stats.lowest_price == 800
        assert stats.highest_price == 1000
        assert stats.data_count == 2

    def test_has_event_in_hours(self, manager: HistoryManager) -> None:
        """指定時間内のイベント確認"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = manager.insert(item)
        manager.insert_event(item_id, "PRICE_DROP", price=800)

        # イベントが記録されていることを確認
        last_event = manager.get_last_event(item_id, "PRICE_DROP")
        assert last_event is not None

    def test_mark_event_notified(self, manager: HistoryManager) -> None:
        """イベントの通知済みマーク"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        item_id = manager.insert(item)
        event_id = manager.insert_event(item_id, "PRICE_DROP", price=800, notified=False)

        manager.mark_event_notified(event_id)

        event = manager.get_last_event(item_id, "PRICE_DROP")
        assert event is not None
        assert event.notified is True

    def test_generate_item_key_static_method(self) -> None:
        """静的メソッド generate_item_key のテスト"""
        key = HistoryManager.generate_item_key(url="https://example.com/item/1")
        assert len(key) == 12

        key_keyword = HistoryManager.generate_item_key(search_keyword="テスト")
        assert len(key_keyword) == 12

    def test_generate_item_key_static_method_with_store_name(self) -> None:
        """静的メソッド generate_item_key に store_name を渡す"""
        key1 = HistoryManager.generate_item_key(search_keyword="テスト", store_name="メルカリ")
        key2 = HistoryManager.generate_item_key(search_keyword="テスト", store_name="ラクマ")
        assert key1 != key2
        assert len(key1) == 12


# === PriceRepository 追加テスト（ブランチカバレッジ） ===
class TestPriceRepositoryBranchCoverage:
    """PriceRepository のブランチカバレッジ向上テスト"""

    @pytest.fixture
    def price_repo(self, temp_data_dir: pathlib.Path) -> PriceRepository:
        """PriceRepository フィクスチャ"""
        db = HistoryDBConnection.create(temp_data_dir)
        db.initialize()
        item_repo = ItemRepository(db=db)
        return PriceRepository(db=db, item_repo=item_repo)

    def test_insert_crawl_failure_after_success(self, price_repo: PriceRepository) -> None:
        """成功後の失敗挿入（既存データを保持）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # まず成功として挿入
        price_repo.insert(item, crawl_status=1)

        # 同じ時間に失敗として挿入（既存の成功データが保持される）
        item["price"] = None
        price_repo.insert(item, crawl_status=0)

        # 価格が保持されていることを確認
        last = price_repo.get_last(url="https://example.com/item/1")
        assert last is not None
        assert last["price"] == 1000

    def test_insert_out_of_stock_with_higher_price(self, price_repo: PriceRepository) -> None:
        """在庫なし時の価格更新（should_update=True パス）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 0,  # 在庫なし
        }

        price_repo.insert(item, crawl_status=1)

        # 同じ時間に異なる価格で挿入
        item["price"] = 1200
        price_repo.insert(item, crawl_status=1)

        # 更新されていることを確認
        last = price_repo.get_last(url="https://example.com/item/1")
        assert last is not None
        assert last["price"] == 1200

    def test_insert_same_price_same_stock_no_update(self, price_repo: PriceRepository) -> None:
        """同じ価格・在庫の挿入（時間のみ更新）"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        price_repo.insert(item, crawl_status=1)

        # 同じデータを再度挿入
        price_repo.insert(item, crawl_status=1)

        # 価格は変わらない
        last = price_repo.get_last(url="https://example.com/item/1")
        assert last is not None
        assert last["price"] == 1000

    def test_get_history_with_days(self, price_repo: PriceRepository) -> None:
        """日数指定での履歴取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 現在時刻でデータを挿入
        price_repo.insert(item, crawl_status=1)

        item["price"] = 900
        price_repo.insert(item, crawl_status=1)

        # 日数を指定して履歴取得
        item_key = url_hash("https://example.com/item/1")
        item_info, history = price_repo.get_history(item_key, days=7)

        assert item_info is not None
        assert len(history) >= 1

    def test_get_stats_with_days(self, price_repo: PriceRepository) -> None:
        """日数指定での統計取得"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        # 現在時刻でデータを挿入（同じ時間のため最小価格が保持される）
        item_id = price_repo.insert(item, crawl_status=1)

        # 日数を指定して統計取得（現在時刻のデータなので7日以内に含まれる）
        stats = price_repo.get_stats(item_id, days=7)
        assert stats["lowest_price"] == 1000
        assert stats["highest_price"] == 1000
        assert stats["data_count"] >= 1

    def test_insert_with_price_change_stock_same(self, price_repo: PriceRepository) -> None:
        """価格変更・在庫同じの挿入"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": 1000,
            "stock": 1,
        }

        price_repo.insert(item, crawl_status=1)

        # 異なる価格で挿入（在庫ありなので最小価格が保持される）
        item["price"] = 1200  # 高い価格
        price_repo.insert(item, crawl_status=1)

        last = price_repo.get_last(url="https://example.com/item/1")
        assert last is not None
        # 在庫ありの場合は最小価格が保持される
        assert last["price"] == 1000

    def test_insert_none_price_to_valid_price(self, price_repo: PriceRepository) -> None:
        """価格なしから価格ありへの更新"""
        item = {
            "name": "テスト商品",
            "store": "test-store",
            "url": "https://example.com/item/1",
            "price": None,
            "stock": 0,
        }

        # まず価格なしで挿入
        price_repo.insert(item, crawl_status=1)

        # 価格を設定して再挿入
        item["price"] = 1000
        item["stock"] = 1
        price_repo.insert(item, crawl_status=1)

        last = price_repo.get_last(url="https://example.com/item/1")
        assert last is not None
        assert last["price"] == 1000
