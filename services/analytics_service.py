"""
统计分析服务，为驾驶舱和运营分析页提供聚合查询。

职责边界：所有统计结果均由数据库实时聚合计算，不使用静态数字
（产品需求 §5.1、§5.6）。本模块不做任何展示层格式化（图表渲染、
颜色映射等），只返回数值和明细，供 pages 层调用。

**指标口径说明（阶段 0 产出的 H1 歧义问题，当前为本阶段的默认假设，
尚未经用户最终确认，后续如有调整需同步修改本文件及文档）：**

    - 履约完成率 = 已签收且 delivered_at <= expected_delivery_at 的订单数
                   / 已到预计送达时间的有效订单数（不含"已取消"）
      "已到预计送达时间"指 expected_delivery_at <= 统计截止时间。
    - 逾期任务数 = due_at 已过且状态不是"已完成"/"已取消"的任务数
      （与 repositories/task_repository.list_overdue 的口径一致）。
    - 平均履约时长 = 已签收订单的 (delivered_at - shipped_at) 平均值（小时）
      采用"发货到签收"而非"下单到签收"，因为下单到发货的时间更多反映
      供应商备货效率，和"履约/物流"概念关系较弱——这是本阶段的判断，
      不是文档强制要求，待确认。
    - 延迟订单占比 = 命中 DELIVERY_OVERDUE 规则的订单数 / 已签收订单总数
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _parse(value: str) -> datetime:
    return datetime.strptime(value, _TIME_FORMAT)


# ----------------------------------------------------------------------
# 驾驶舱 KPI（产品需求 §5.1）
# ----------------------------------------------------------------------


def get_dashboard_kpis(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """驾驶舱核心指标：订单总量、异常订单数、待处理异常数、履约完成率、
    逾期任务数。
    """
    now = now or datetime.now()
    now_iso = now.strftime(_TIME_FORMAT)

    total_orders = conn.execute("SELECT COUNT(*) AS n FROM orders").fetchone()["n"]

    anomaly_order_count = conn.execute(
        "SELECT COUNT(DISTINCT order_id) AS n FROM anomalies"
    ).fetchone()["n"]

    pending_anomaly_count = conn.execute(
        "SELECT COUNT(*) AS n FROM anomalies WHERE status = '待确认'"
    ).fetchone()["n"]

    fulfillment_rate = compute_fulfillment_rate(conn, now)

    overdue_task_count = conn.execute(
        "SELECT COUNT(*) AS n FROM operation_tasks WHERE due_at < ? AND status NOT IN ('已完成', '已取消')",
        (now_iso,),
    ).fetchone()["n"]

    return {
        "total_orders": total_orders,
        "anomaly_order_count": anomaly_order_count,
        "pending_anomaly_count": pending_anomaly_count,
        "fulfillment_rate": fulfillment_rate,
        "overdue_task_count": overdue_task_count,
    }


def compute_fulfillment_rate(conn: sqlite3.Connection, now: datetime | None = None) -> float | None:
    """履约完成率 = 已签收且按时的订单数 / 已到预计送达时间的有效订单数。

    返回 None 表示分母为 0（没有足够样本），调用方应展示"暂无数据"
    而不是 0%（0% 会被误解为"完全没履约好"，而实际是"没有可统计样本"）。
    """
    now = now or datetime.now()
    now_iso = now.strftime(_TIME_FORMAT)

    denominator = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE status != '已取消' AND expected_delivery_at <= ?",
        (now_iso,),
    ).fetchone()["n"]

    if denominator == 0:
        return None

    numerator = conn.execute(
        """SELECT COUNT(*) AS n FROM orders
           WHERE status = '已签收' AND delivered_at IS NOT NULL
             AND delivered_at <= expected_delivery_at
             AND expected_delivery_at <= ?""",
        (now_iso,),
    ).fetchone()["n"]

    return round(numerator / denominator * 100, 1)


def get_order_trend(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    """按日统计订单量趋势，用于驾驶舱趋势图（产品需求 §5.1）。

    返回最近 N 天每天的订单数量，按 order_date 的日期部分分组。
    """
    rows = conn.execute(
        f"""SELECT substr(order_date, 1, 10) AS day, COUNT(*) AS n
            FROM orders
            GROUP BY day
            ORDER BY day DESC
            LIMIT ?""",
        (days,),
    ).fetchall()
    return [{"day": r["day"], "count": r["n"]} for r in reversed(rows)]


def get_anomaly_type_distribution(conn: sqlite3.Connection) -> list[dict]:
    """按异常类型统计数量，用于驾驶舱异常分布（产品需求 §5.1）。"""
    rows = conn.execute(
        "SELECT anomaly_type, COUNT(*) AS n FROM anomalies GROUP BY anomaly_type ORDER BY n DESC"
    ).fetchall()
    return [{"anomaly_type": r["anomaly_type"], "count": r["n"]} for r in rows]


def get_risk_distribution(conn: sqlite3.Connection) -> list[dict]:
    """按高/中/低风险统计异常数量，用于驾驶舱风险分布（产品需求 §5.1）。"""
    rows = conn.execute(
        "SELECT severity, COUNT(*) AS n FROM anomalies GROUP BY severity"
    ).fetchall()
    order = {"高": 0, "中": 1, "低": 2}
    result = [{"severity": r["severity"], "count": r["n"]} for r in rows]
    result.sort(key=lambda x: order.get(x["severity"], 99))
    return result


# ----------------------------------------------------------------------
# 运营分析页（产品需求 §5.6）
# ----------------------------------------------------------------------


def get_fulfillment_analytics(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """履约表现分析：履约完成率、平均履约时长、延迟订单占比。"""
    now = now or datetime.now()

    fulfillment_rate = compute_fulfillment_rate(conn, now)

    delivered_rows = conn.execute(
        "SELECT shipped_at, delivered_at FROM orders WHERE status = '已签收' AND delivered_at IS NOT NULL AND shipped_at IS NOT NULL"
    ).fetchall()
    if delivered_rows:
        total_hours = sum(
            (_parse(r["delivered_at"]) - _parse(r["shipped_at"])).total_seconds() / 3600
            for r in delivered_rows
        )
        avg_fulfillment_hours = round(total_hours / len(delivered_rows), 1)
    else:
        avg_fulfillment_hours = None

    delivered_count = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE status = '已签收'"
    ).fetchone()["n"]
    delayed_count = conn.execute(
        "SELECT COUNT(*) AS n FROM anomalies WHERE rule_code = 'DELIVERY_OVERDUE'"
    ).fetchone()["n"]
    delayed_ratio = round(delayed_count / delivered_count * 100, 1) if delivered_count else None

    return {
        "fulfillment_rate": fulfillment_rate,
        "avg_fulfillment_hours": avg_fulfillment_hours,
        "delayed_order_ratio": delayed_ratio,
        "sample_size": {
            "fulfillment_rate_denominator": None,  # 由 compute_fulfillment_rate 内部计算，此处不重复查询
            "avg_fulfillment_hours_sample": len(delivered_rows),
            "delivered_order_count": delivered_count,
        },
    }


def get_anomaly_analytics(conn: sqlite3.Connection) -> dict:
    """异常分析：异常数量趋势、异常类型分布、风险等级分布
    （产品需求 §5.6）。
    """
    return {
        "type_distribution": get_anomaly_type_distribution(conn),
        "risk_distribution": get_risk_distribution(conn),
        "total_count": conn.execute("SELECT COUNT(*) AS n FROM anomalies").fetchone()["n"],
    }


def get_customer_anomaly_analytics(conn: sqlite3.Connection, top_n: int = 10) -> list[dict]:
    """客户分析：按客户统计异常订单分布，取异常数最多的 top_n 个客户
    （产品需求 §5.6："客户异常订单分布、重点客户异常情况"）。
    """
    rows = conn.execute(
        """SELECT c.customer_id, c.name, c.tier, COUNT(DISTINCT a.anomaly_id) AS anomaly_count
           FROM customers c
           JOIN orders o ON o.customer_id = c.customer_id
           JOIN anomalies a ON a.order_id = o.order_id
           GROUP BY c.customer_id
           ORDER BY anomaly_count DESC
           LIMIT ?""",
        (top_n,),
    ).fetchall()
    return [
        {
            "customer_id": r["customer_id"],
            "name": r["name"],
            "tier": r["tier"],
            "anomaly_count": r["anomaly_count"],
        }
        for r in rows
    ]


def get_task_analytics(conn: sqlite3.Connection, now: datetime | None = None) -> dict:
    """任务分析：任务完成率、平均处理时长、逾期任务数
    （产品需求 §5.6）。
    """
    now = now or datetime.now()
    now_iso = now.strftime(_TIME_FORMAT)

    total = conn.execute("SELECT COUNT(*) AS n FROM operation_tasks").fetchone()["n"]
    completed = conn.execute(
        "SELECT COUNT(*) AS n FROM operation_tasks WHERE status = '已完成'"
    ).fetchone()["n"]
    completion_rate = round(completed / total * 100, 1) if total else None

    completed_rows = conn.execute(
        "SELECT created_at, completed_at FROM operation_tasks WHERE status = '已完成' AND completed_at IS NOT NULL"
    ).fetchall()
    if completed_rows:
        total_hours = sum(
            (_parse(r["completed_at"]) - _parse(r["created_at"])).total_seconds() / 3600
            for r in completed_rows
        )
        avg_processing_hours = round(total_hours / len(completed_rows), 1)
    else:
        avg_processing_hours = None

    overdue_count = conn.execute(
        "SELECT COUNT(*) AS n FROM operation_tasks WHERE due_at < ? AND status NOT IN ('已完成', '已取消')",
        (now_iso,),
    ).fetchone()["n"]

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": completion_rate,
        "avg_processing_hours": avg_processing_hours,
        "overdue_count": overdue_count,
        "sample_size": {"avg_processing_hours_sample": len(completed_rows)},
    }
