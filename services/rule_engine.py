"""
异常规则引擎。

职责边界（阶段 0 确认、技术方案 §5 要求）：
    - 本模块是全系统**唯一**做异常触发判断的地方。页面代码、其他 service
      都不得重复实现这些判断逻辑。
    - 规则判断是确定性的（基于明确的字段比较），不涉及任何 AI/LLM 调用。
    - 所有阈值从 config/anomaly_rules.py 读取，不在本文件硬编码数值。
    - 每条判断结果都带 evidence（触发依据的具体字段值），保证可复核
      （产品需求 §5.4.2 对 AI 诊断的可追溯性要求，此处是规则引擎层面的
      对应实现——规则判断本身就应该是可解释、可复核的）。

本模块不访问数据库——它只接受已经从数据库查出来的订单数据（sqlite3.Row
或兼容的映射对象），返回判断结果。这样规则逻辑可以脱离数据库独立测试
（技术方案 §9："为异常规则编写单元测试，覆盖正例、反例和边界时间"）。
"""

from __future__ import annotations

from datetime import datetime

from config.anomaly_rules import (
    RULE_SHIP_OVERDUE,
    RULE_DELIVERY_STALLED,
    RULE_DELIVERY_OVERDUE,
    RULE_SUPPLIER_PREP_DELAY,
    RULE_STATUS_CONFLICT,
    DELIVERY_STALLED_HOURS,
    SUPPLIER_PREP_DELAY_HOURS,
    STATUS_CONFLICT_PAIRS,
)
from models.schemas import RuleViolation

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _parse(value: str) -> datetime:
    return datetime.strptime(value, _TIME_FORMAT)


def check_ship_overdue(order_row, now: datetime) -> RuleViolation | None:
    """SHIP_OVERDUE：当前日期晚于预计发货时间，且订单仍未发货，且订单未取消。

    技术方案 §5 判断条件原文：
        "now > expected_ship_at 且 shipped_at 为空且订单未取消"
    """
    if order_row["status"] == "已取消":
        return None
    if order_row["shipped_at"] is not None:
        return None

    expected_ship_at = _parse(order_row["expected_ship_at"])
    if now > expected_ship_at:
        return RuleViolation(
            order_id=order_row["order_id"],
            rule_code=RULE_SHIP_OVERDUE,
            anomaly_type="超时未发货",
            severity="高",
            evidence={
                "expected_ship_at": order_row["expected_ship_at"],
                "current_time": now.strftime(_TIME_FORMAT),
                "order_status": order_row["status"],
                "shipped_at": "未发货",
            },
        )
    return None


def check_delivery_stalled(order_row, now: datetime) -> RuleViolation | None:
    """DELIVERY_STALLED：物流最后更新时间超过配置阈值，且未签收。

    技术方案 §5 判断条件原文：
        "物流最后更新时间超过配置阈值，且未签收"
    依赖字段：logistics_status、logistics_last_updated_at（通过
    order_repository.list_all_with_logistics 的 JOIN 结果提供）。
    """
    logistics_status = order_row["logistics_status"]
    last_updated_raw = order_row["logistics_last_updated_at"]

    if logistics_status is None or last_updated_raw is None:
        # 没有物流记录（例如尚未发货的订单），不在本规则判断范围内。
        return None
    if logistics_status == "已签收":
        return None

    last_updated_at = _parse(last_updated_raw)
    hours_since_update = (now - last_updated_at).total_seconds() / 3600

    if hours_since_update > DELIVERY_STALLED_HOURS:
        return RuleViolation(
            order_id=order_row["order_id"],
            rule_code=RULE_DELIVERY_STALLED,
            anomaly_type="物流延迟",
            severity="中",
            evidence={
                "logistics_last_updated_at": last_updated_raw,
                "current_time": now.strftime(_TIME_FORMAT),
                "hours_since_update": f"{hours_since_update:.1f}",
                "threshold_hours": str(DELIVERY_STALLED_HOURS),
                "logistics_status": logistics_status,
            },
        )
    return None


def check_delivery_overdue(order_row, now: datetime) -> RuleViolation | None:
    """DELIVERY_OVERDUE：订单已签收，但实际签收时间晚于预计送达时间。

    技术方案 §5 判断条件原文："delivered_at > expected_delivery_at"
    """
    delivered_at_raw = order_row["delivered_at"]
    if delivered_at_raw is None:
        return None

    delivered_at = _parse(delivered_at_raw)
    expected_delivery_at = _parse(order_row["expected_delivery_at"])

    if delivered_at > expected_delivery_at:
        return RuleViolation(
            order_id=order_row["order_id"],
            rule_code=RULE_DELIVERY_OVERDUE,
            anomaly_type="履约超时",
            severity="中",
            evidence={
                "delivered_at": delivered_at_raw,
                "expected_delivery_at": order_row["expected_delivery_at"],
                "overdue_hours": f"{(delivered_at - expected_delivery_at).total_seconds() / 3600:.1f}",
            },
        )
    return None


def check_supplier_prep_delay(order_row, now: datetime) -> RuleViolation | None:
    """SUPPLIER_PREP_DELAY：供应商备货状态更新时间超过配置阈值仍未更新
    （即仍未达到"备货完成"）。

    技术方案 §5 判断条件原文："备货状态更新时间超过配置阈值"
    依赖字段：supplier_prep_status、supplier_prep_updated_at
    （阶段 2 新增字段，见 database/schema.sql 说明，用户已确认）。
    """
    prep_status = order_row["supplier_prep_status"]
    prep_updated_raw = order_row["supplier_prep_updated_at"]

    if prep_status == "备货完成":
        return None

    prep_updated_at = _parse(prep_updated_raw)
    hours_since_update = (now - prep_updated_at).total_seconds() / 3600

    if hours_since_update > SUPPLIER_PREP_DELAY_HOURS:
        return RuleViolation(
            order_id=order_row["order_id"],
            rule_code=RULE_SUPPLIER_PREP_DELAY,
            anomaly_type="供应商备货异常",
            severity="中",
            evidence={
                "supplier_prep_status": prep_status,
                "supplier_prep_updated_at": prep_updated_raw,
                "current_time": now.strftime(_TIME_FORMAT),
                "hours_since_update": f"{hours_since_update:.1f}",
                "threshold_hours": str(SUPPLIER_PREP_DELAY_HOURS),
            },
        )
    return None


def check_status_conflict(order_row, now: datetime) -> RuleViolation | None:
    """STATUS_CONFLICT：订单状态与物流状态命中预定义不合理组合。

    技术方案 §5 判断条件原文："订单与物流状态命中预定义不合理组合"
    冲突组合清单来自 config/anomaly_rules.py 的 STATUS_CONFLICT_PAIRS
    （阶段 0 的 H2 歧义问题，当前为默认假设清单，不是完整定义）。
    """
    order_status = order_row["status"]
    logistics_status = order_row["logistics_status"]

    if logistics_status is None:
        return None

    if (order_status, logistics_status) in STATUS_CONFLICT_PAIRS:
        return RuleViolation(
            order_id=order_row["order_id"],
            rule_code=RULE_STATUS_CONFLICT,
            anomaly_type="订单状态异常",
            severity="高",
            evidence={
                "order_status": order_status,
                "logistics_status": logistics_status,
                "conflict_rule": f"({order_status}, {logistics_status}) 命中预定义冲突组合",
            },
        )
    return None


# 所有规则检查函数的统一列表，供批量扫描使用。
ALL_RULE_CHECKS = (
    check_ship_overdue,
    check_delivery_stalled,
    check_delivery_overdue,
    check_supplier_prep_delay,
    check_status_conflict,
)


def check_order(order_row, now: datetime | None = None) -> list[RuleViolation]:
    """对单条订单（含物流 JOIN 结果）运行全部规则检查，返回所有命中的违规。

    一条订单可能同时命中多条规则（例如既超时未发货又状态冲突），
    全部返回，由调用方（anomaly_service）决定如何分别处理。
    """
    now = now or datetime.now()
    violations = []
    for check_fn in ALL_RULE_CHECKS:
        result = check_fn(order_row, now)
        if result is not None:
            violations.append(result)
    return violations


def scan_orders(order_rows, now: datetime | None = None) -> list[RuleViolation]:
    """对一批订单运行全部规则检查，返回所有命中的违规（不去重，不写数据库）。

    去重（同订单同规则在活跃状态下只保留一条）是 anomaly_service 的职责，
    本函数只负责"纯规则判断"这一层。
    """
    now = now or datetime.now()
    all_violations: list[RuleViolation] = []
    for row in order_rows:
        all_violations.extend(check_order(row, now))
    return all_violations
