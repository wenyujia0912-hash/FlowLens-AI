"""
订单业务服务。

职责边界：聚合订单详情所需的关联数据（商品明细、履约时间线、供应商信息、
物流节点、关联异常），不包含任何异常判断逻辑（那是 rule_engine 的职责）。
"""

from __future__ import annotations

import sqlite3

from repositories import (
    order_repository,
    customer_repository,
    anomaly_repository,
)
from models.schemas import OrderDetail, Supplier


def search_orders(
    conn: sqlite3.Connection,
    *,
    order_id: str | None = None,
    customer_id: str | None = None,
    status: str | None = None,
    logistics_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """返回订单列表，每条附带是否有关联异常的标记
    （产品需求 §5.3：订单列表字段含异常标记）。
    """
    orders = order_repository.list_all(
        conn,
        order_id_contains=order_id,
        customer_id=customer_id,
        status=status,
        logistics_status=logistics_status,
        date_from=date_from,
        date_to=date_to,
    )
    result = []
    for o in orders:
        anomalies = anomaly_repository.list_by_order(conn, o.order_id)
        result.append({"order": o, "has_anomaly": len(anomalies) > 0, "anomaly_count": len(anomalies)})
    return result


def get_order_detail(conn: sqlite3.Connection, order_id: str) -> OrderDetail | None:
    """订单详情聚合：订单基本信息 + 商品明细 + 供应商信息 + 物流节点 +
    关联异常（产品需求 §5.3；页面交互设计 §3.3）。

    履约时间线由调用方（页面层）基于 order 和 logistics.events 的时间字段
    自行排序展示；本服务只保证返回的数据本身真实、不编造缺失的时间
    （页面交互设计 §3.3："缺失的实际时间不得伪造"）。
    """
    order = order_repository.get_by_id(conn, order_id)
    if order is None:
        return None

    customer = customer_repository.get_by_id(conn, order.customer_id)
    if customer is None:
        raise RuntimeError(f"数据完整性问题：订单 {order_id} 的客户 {order.customer_id} 不存在")

    # 供应商查询：直接复用 order_repository 的连接做一次最小查询，
    # 不新建 supplier_service（阶段 0/1 确认的目录结构里供应商没有
    # 独立 service，查询需求较简单，直接在此聚合）。
    supplier_row = conn.execute(
        "SELECT * FROM suppliers WHERE supplier_id = ?", (order.supplier_id,)
    ).fetchone()
    if supplier_row is None:
        raise RuntimeError(f"数据完整性问题：订单 {order_id} 的供应商 {order.supplier_id} 不存在")

    supplier = Supplier(
        supplier_id=supplier_row["supplier_id"],
        name=supplier_row["name"],
        category=supplier_row["category"],
        status=supplier_row["status"],
        lead_time_days=supplier_row["lead_time_days"],
    )

    items = order_repository.list_items_for_order(conn, order_id)
    logistics = order_repository.get_logistics_for_order(conn, order_id)
    anomalies = anomaly_repository.list_by_order(conn, order_id)

    return OrderDetail(
        order=order,
        customer=customer,
        supplier=supplier,
        items=items,
        logistics=logistics,
        anomaly_ids=[a.anomaly_id for a in anomalies],
    )
