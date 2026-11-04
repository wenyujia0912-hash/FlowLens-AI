"""
规则引擎单元测试。

对应技术方案 §9："为异常规则编写单元测试，覆盖正例、反例和边界时间。"

本测试文件只依赖标准库 unittest，不依赖 pytest（避免引入未确认的测试框架
依赖）。构造的订单数据是最小化的字典（模拟 sqlite3.Row 的字段访问方式），
不依赖真实数据库，可独立运行。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from services import rule_engine


class FakeRow(dict):
    """最小化模拟 sqlite3.Row：支持 row["field"] 访问方式。"""

    def __getitem__(self, key):
        return super().__getitem__(key)


def _base_order(**overrides) -> FakeRow:
    base = {
        "order_id": "ORD-TEST001",
        "status": "待发货",
        "order_date": "2024-03-01T10:00:00",
        "expected_ship_at": "2024-03-03T10:00:00",
        "shipped_at": None,
        "expected_delivery_at": "2024-03-10T10:00:00",
        "delivered_at": None,
        "supplier_prep_status": "备货完成",
        "supplier_prep_updated_at": "2024-03-01T12:00:00",
        "logistics_status": None,
        "logistics_last_updated_at": None,
        "logistics_estimated_delivery_at": None,
    }
    base.update(overrides)
    return FakeRow(base)


class TestShipOverdue(unittest.TestCase):
    def test_positive_not_shipped_past_deadline(self):
        """正例：预计发货时间已过，仍未发货，订单未取消 → 应触发。"""
        now = datetime(2024, 3, 5, 10, 0, 0)  # 晚于 expected_ship_at
        order = _base_order(status="待发货", shipped_at=None)
        result = rule_engine.check_ship_overdue(order, now)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, "SHIP_OVERDUE")

    def test_negative_already_shipped(self):
        """反例：预计发货时间已过，但已经发货 → 不应触发。"""
        now = datetime(2024, 3, 5, 10, 0, 0)
        order = _base_order(status="运输中", shipped_at="2024-03-04T10:00:00")
        result = rule_engine.check_ship_overdue(order, now)
        self.assertIsNone(result)

    def test_negative_order_cancelled(self):
        """反例：订单已取消 → 不应触发，即使未发货且已过预计发货时间。"""
        now = datetime(2024, 3, 5, 10, 0, 0)
        order = _base_order(status="已取消", shipped_at=None)
        result = rule_engine.check_ship_overdue(order, now)
        self.assertIsNone(result)

    def test_boundary_exact_deadline(self):
        """边界：当前时间恰好等于预计发货时间 → 不应触发（判断条件是严格大于）。"""
        now = datetime.strptime("2024-03-03T10:00:00", "%Y-%m-%dT%H:%M:%S")
        order = _base_order(status="待发货", shipped_at=None)
        result = rule_engine.check_ship_overdue(order, now)
        self.assertIsNone(result)

    def test_boundary_one_second_past_deadline(self):
        """边界：当前时间比预计发货时间晚 1 秒 → 应触发。"""
        now = datetime.strptime("2024-03-03T10:00:00", "%Y-%m-%dT%H:%M:%S") + timedelta(seconds=1)
        order = _base_order(status="待发货", shipped_at=None)
        result = rule_engine.check_ship_overdue(order, now)
        self.assertIsNotNone(result)


class TestDeliveryStalled(unittest.TestCase):
    def test_positive_stalled_past_threshold(self):
        """正例：物流最后更新超过阈值（48小时），未签收 → 应触发。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            logistics_status="运输中",
            logistics_last_updated_at="2024-03-07T09:00:00",
        )
        result = rule_engine.check_delivery_stalled(order, now)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, "DELIVERY_STALLED")

    def test_negative_within_threshold(self):
        """反例：最后更新时间在阈值内 → 不应触发。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            logistics_status="运输中",
            logistics_last_updated_at="2024-03-09T10:00:00",  # 24h 前，阈值48h内
        )
        result = rule_engine.check_delivery_stalled(order, now)
        self.assertIsNone(result)

    def test_negative_already_delivered(self):
        """反例：已签收 → 不应触发，即使最后更新时间很久以前。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            logistics_status="已签收",
            logistics_last_updated_at="2024-02-01T10:00:00",
        )
        result = rule_engine.check_delivery_stalled(order, now)
        self.assertIsNone(result)

    def test_negative_no_logistics_record(self):
        """反例：没有物流记录（未发货）→ 不应触发。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(logistics_status=None, logistics_last_updated_at=None)
        result = rule_engine.check_delivery_stalled(order, now)
        self.assertIsNone(result)

    def test_boundary_exact_threshold_hours(self):
        """边界：恰好等于阈值小时数 → 不应触发（判断条件是严格大于）。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        last_update = now - timedelta(hours=48)
        order = _base_order(
            logistics_status="运输中",
            logistics_last_updated_at=last_update.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        result = rule_engine.check_delivery_stalled(order, now)
        self.assertIsNone(result)


class TestDeliveryOverdue(unittest.TestCase):
    def test_positive_delivered_after_expected(self):
        """正例：实际签收晚于预计送达 → 应触发。"""
        order = _base_order(
            expected_delivery_at="2024-03-10T10:00:00",
            delivered_at="2024-03-11T08:00:00",
        )
        result = rule_engine.check_delivery_overdue(order, datetime.now())
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, "DELIVERY_OVERDUE")

    def test_negative_delivered_before_expected(self):
        """反例：实际签收早于预计送达 → 不应触发。"""
        order = _base_order(
            expected_delivery_at="2024-03-10T10:00:00",
            delivered_at="2024-03-09T08:00:00",
        )
        result = rule_engine.check_delivery_overdue(order, datetime.now())
        self.assertIsNone(result)

    def test_negative_not_delivered_yet(self):
        """反例：尚未签收（delivered_at 为空）→ 不应触发。"""
        order = _base_order(delivered_at=None)
        result = rule_engine.check_delivery_overdue(order, datetime.now())
        self.assertIsNone(result)

    def test_boundary_exact_expected_time(self):
        """边界：实际签收时间恰好等于预计送达时间 → 不应触发。"""
        order = _base_order(
            expected_delivery_at="2024-03-10T10:00:00",
            delivered_at="2024-03-10T10:00:00",
        )
        result = rule_engine.check_delivery_overdue(order, datetime.now())
        self.assertIsNone(result)


class TestSupplierPrepDelay(unittest.TestCase):
    def test_positive_delayed_prep(self):
        """正例：备货未完成且更新时间超过阈值（72小时）→ 应触发。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            supplier_prep_status="待备货",
            supplier_prep_updated_at="2024-03-05T10:00:00",  # 5天前，远超72h
        )
        result = rule_engine.check_supplier_prep_delay(order, now)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, "SUPPLIER_PREP_DELAY")

    def test_negative_prep_completed(self):
        """反例：备货已完成 → 不应触发，即使更新时间很久以前。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            supplier_prep_status="备货完成",
            supplier_prep_updated_at="2024-02-01T10:00:00",
        )
        result = rule_engine.check_supplier_prep_delay(order, now)
        self.assertIsNone(result)

    def test_negative_within_threshold(self):
        """反例：更新时间在阈值内 → 不应触发。"""
        now = datetime(2024, 3, 10, 10, 0, 0)
        order = _base_order(
            supplier_prep_status="备货中",
            supplier_prep_updated_at="2024-03-08T10:00:00",  # 48h前，阈值72h内
        )
        result = rule_engine.check_supplier_prep_delay(order, now)
        self.assertIsNone(result)


class TestStatusConflict(unittest.TestCase):
    def test_positive_cancelled_but_shipping(self):
        """正例：订单已取消但物流仍在运输中 → 命中冲突组合，应触发。"""
        order = _base_order(status="已取消", logistics_status="运输中")
        result = rule_engine.check_status_conflict(order, datetime.now())
        self.assertIsNotNone(result)
        self.assertEqual(result.rule_code, "STATUS_CONFLICT")

    def test_negative_normal_combination(self):
        """反例：运输中 + 运输中 是合理组合 → 不应触发。"""
        order = _base_order(status="运输中", logistics_status="运输中")
        result = rule_engine.check_status_conflict(order, datetime.now())
        self.assertIsNone(result)

    def test_negative_no_logistics(self):
        """反例：没有物流记录 → 不应触发。"""
        order = _base_order(status="待确认", logistics_status=None)
        result = rule_engine.check_status_conflict(order, datetime.now())
        self.assertIsNone(result)


class TestCheckOrderMultipleViolations(unittest.TestCase):
    def test_order_can_trigger_multiple_rules(self):
        """一条订单可能同时命中多条规则，check_order 应全部返回。"""
        now = datetime(2024, 3, 5, 10, 0, 0)
        order = _base_order(
            status="待发货",
            shipped_at=None,  # 触发 SHIP_OVERDUE
            supplier_prep_status="待备货",
            supplier_prep_updated_at="2024-03-01T10:00:00",  # 触发 SUPPLIER_PREP_DELAY
        )
        results = rule_engine.check_order(order, now)
        rule_codes = {r.rule_code for r in results}
        self.assertIn("SHIP_OVERDUE", rule_codes)
        self.assertIn("SUPPLIER_PREP_DELAY", rule_codes)

    def test_normal_order_triggers_nothing(self):
        """完全正常的订单不应触发任何规则。"""
        now = datetime(2024, 3, 15, 10, 0, 0)
        order = _base_order(
            status="已签收",
            shipped_at="2024-03-03T10:00:00",
            delivered_at="2024-03-09T10:00:00",
            expected_delivery_at="2024-03-10T10:00:00",
            supplier_prep_status="备货完成",
            logistics_status="已签收",
            logistics_last_updated_at="2024-03-09T10:00:00",
        )
        results = rule_engine.check_order(order, now)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
