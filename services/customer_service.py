"""
客户业务服务。

职责边界：聚合客户详情所需的关联数据（订单数、异常数、累计金额），
确保这些数字始终来自数据库实时查询，不在任何地方缓存为静态值
（产品需求 §5.2 的硬性要求）。
"""

from __future__ import annotations

import sqlite3

from models.schemas import Customer
from repositories import customer_repository, order_repository, anomaly_repository


def search_customers(
    conn: sqlite3.Connection,
    *,
    name: str | None = None,
    industry: str | None = None,
    tier: str | None = None,
    status: str | None = None,
) -> list[dict]:
    """返回客户列表，每条附带实时计算的订单数/异常数/累计金额
    （列表页字段，产品需求 §5.2）。
    """
    customers = customer_repository.list_all(
        conn, name_contains=name, industry=industry, tier=tier, status=status
    )
    result = []
    for c in customers:
        result.append(
            {
                "customer": c,
                "order_count": customer_repository.count_orders_for_customer(conn, c.customer_id),
                "total_amount": customer_repository.sum_order_amount_for_customer(conn, c.customer_id),
                "anomaly_count": customer_repository.count_anomalies_for_customer(conn, c.customer_id),
            }
        )
    return result


def get_customer_detail(conn: sqlite3.Connection, customer_id: str) -> dict | None:
    """客户详情：基本资料 + 关联订单 + 关联异常（产品需求 §5.2）。"""
    customer = customer_repository.get_by_id(conn, customer_id)
    if customer is None:
        return None

    orders = order_repository.list_by_customer(conn, customer_id)
    order_ids = [o.order_id for o in orders]

    anomalies = []
    for order_id in order_ids:
        anomalies.extend(anomaly_repository.list_by_order(conn, order_id))

    return {
        "customer": customer,
        "orders": orders,
        "anomalies": anomalies,
        "order_count": len(orders),
        "anomaly_count": len(anomalies),
        "total_amount": sum(o.amount for o in orders),
    }
