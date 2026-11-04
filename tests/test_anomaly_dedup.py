"""
异常去重策略测试。

对应技术方案 §5、§9："测试重复执行异常扫描时不会重复创建活跃异常。"
使用真实临时数据库 + 真实 seed_data 生成器的最小子集，验证
anomaly_service.scan_and_create_anomalies 在重复调用时的幂等行为。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from database.connection import get_connection
from services import anomaly_service


class TestAnomalyDedup(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "test.db"
        schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_path.read_text(encoding="utf-8"))

        # 插入一条最小化的、必定触发 SHIP_OVERDUE 的订单。
        conn.execute(
            """INSERT INTO customers (customer_id, name, industry, tier, status, created_at)
               VALUES ('CUST-1', '测试客户', '测试行业', '普通客户', '合作中', '2024-01-01T00:00:00')"""
        )
        conn.execute(
            """INSERT INTO suppliers (supplier_id, name, category, status, lead_time_days)
               VALUES ('SUPP-1', '测试供应商', '测试类别', '合作中', 5)"""
        )
        conn.execute(
            """INSERT INTO orders (
                   order_id, customer_id, supplier_id, order_date, amount, status,
                   expected_ship_at, shipped_at, expected_delivery_at, delivered_at,
                   supplier_prep_status, supplier_prep_updated_at
               ) VALUES (
                   'ORD-1', 'CUST-1', 'SUPP-1', '2024-03-01T10:00:00', 1000.0, '待发货',
                   '2024-03-03T10:00:00', NULL, '2024-03-10T10:00:00', NULL,
                   '备货完成', '2024-03-01T12:00:00'
               )"""
        )
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_repeated_scan_does_not_duplicate_active_anomaly(self):
        """核心验收点：重新运行异常扫描，不重复创建同一条活跃异常。"""
        now = datetime(2024, 3, 5, 10, 0, 0)  # 晚于 expected_ship_at，应触发

        with get_connection(self.db_path) as conn:
            result1 = anomaly_service.scan_and_create_anomalies(conn, now)
        self.assertEqual(result1["created"], 1)
        self.assertEqual(result1["skipped_duplicate"], 0)

        # 第二次扫描：同一条订单、同一规则，应被去重跳过。
        with get_connection(self.db_path) as conn:
            result2 = anomaly_service.scan_and_create_anomalies(conn, now)
        self.assertEqual(result2["created"], 0)
        self.assertEqual(result2["skipped_duplicate"], 1)

        # 数据库中应该只有一条该订单该规则的异常记录。
        with get_connection(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM anomalies WHERE order_id = 'ORD-1' AND rule_code = 'SHIP_OVERDUE'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_scan_three_times_still_one_anomaly(self):
        """多次重复扫描（3次）仍只有一条活跃异常。"""
        now = datetime(2024, 3, 5, 10, 0, 0)

        for _ in range(3):
            with get_connection(self.db_path) as conn:
                anomaly_service.scan_and_create_anomalies(conn, now)

        with get_connection(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM anomalies WHERE order_id = 'ORD-1'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_new_anomaly_allowed_after_closing_previous(self):
        """如果之前的异常已关闭（非活跃状态），再次扫描应允许创建新异常
        （去重只针对"活跃"状态，技术方案 §5 的去重键包含"活跃状态"这个
        限定条件）。
        """
        now = datetime(2024, 3, 5, 10, 0, 0)

        with get_connection(self.db_path) as conn:
            anomaly_service.scan_and_create_anomalies(conn, now)

        with get_connection(self.db_path) as conn:
            anomaly_id = conn.execute(
                "SELECT anomaly_id FROM anomalies WHERE order_id = 'ORD-1'"
            ).fetchone()[0]
            anomaly_service.mark_closed(conn, anomaly_id, now)

        # 异常已关闭，再次扫描应该创建一条新的异常记录。
        with get_connection(self.db_path) as conn:
            result = anomaly_service.scan_and_create_anomalies(conn, now)
        self.assertEqual(result["created"], 1)

        with get_connection(self.db_path) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM anomalies WHERE order_id = 'ORD-1'"
            ).fetchone()[0]
        self.assertEqual(total, 2)  # 一条已关闭 + 一条新的


if __name__ == "__main__":
    unittest.main()
