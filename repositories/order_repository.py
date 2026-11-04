"""
订单数据访问层。

职责边界：仅做订单、商品明细、物流及物流节点的 SQL 读写，不包含任何
"订单是否异常"之类的业务判断（那是 rule_engine 和 anomaly_service 的职责）。
"""

from __future__ import annotations

import sqlite3

from models.schemas import Logistics, LogisticsEvent, Order, OrderItem


def _row_to_order(row: sqlite3.Row) -> Order:
    return Order(
        order_id=row["order_id"],
        customer_id=row["customer_id"],
        supplier_id=row["supplier_id"],
        order_date=row["order_date"],
        amount=row["amount"],
        status=row["status"],
        expected_ship_at=row["expected_ship_at"],
        shipped_at=row["shipped_at"],
        expected_delivery_at=row["expected_delivery_at"],
        delivered_at=row["delivered_at"],
        supplier_prep_status=row["supplier_prep_status"],
        supplier_prep_updated_at=row["supplier_prep_updated_at"],
    )


def get_by_id(conn: sqlite3.Connection, order_id: str) -> Order | None:
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return _row_to_order(row) if row else None


def list_all(
    conn: sqlite3.Connection,
    *,
    order_id_contains: str | None = None,
    customer_id: str | None = None,
    status: str | None = None,
    logistics_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[Order]:
    """列出订单，支持按编号搜索、客户/订单状态/物流状态/日期筛选。

    对应产品需求 §5.3："支持按订单编号搜索，按客户、订单状态、履约状态和
    日期筛选。"
    """
    clauses: list[str] = []
    params: list[str] = []
    joins = ""

    if logistics_status:
        joins = "JOIN logistics l ON l.order_id = o.order_id"
        clauses.append("l.current_status = ?")
        params.append(logistics_status)

    if order_id_contains:
        clauses.append("o.order_id LIKE ?")
        params.append(f"%{order_id_contains}%")
    if customer_id:
        clauses.append("o.customer_id = ?")
        params.append(customer_id)
    if status:
        clauses.append("o.status = ?")
        params.append(status)
    if date_from:
        clauses.append("o.order_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("o.order_date <= ?")
        params.append(date_to)

    sql = f"SELECT o.* FROM orders o {joins}"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY o.order_date DESC"

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_order(r) for r in rows]


def list_by_customer(conn: sqlite3.Connection, customer_id: str) -> list[Order]:
    rows = conn.execute(
        "SELECT * FROM orders WHERE customer_id = ? ORDER BY order_date DESC",
        (customer_id,),
    ).fetchall()
    return [_row_to_order(r) for r in rows]


def list_items_for_order(conn: sqlite3.Connection, order_id: str) -> list[OrderItem]:
    rows = conn.execute(
        "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    return [
        OrderItem(
            item_id=r["item_id"],
            order_id=r["order_id"],
            product_name=r["product_name"],
            quantity=r["quantity"],
            unit_price=r["unit_price"],
        )
        for r in rows
    ]


def get_logistics_for_order(conn: sqlite3.Connection, order_id: str) -> Logistics | None:
    row = conn.execute(
        "SELECT * FROM logistics WHERE order_id = ?", (order_id,)
    ).fetchone()
    if not row:
        return None

    event_rows = conn.execute(
        """SELECT * FROM logistics_events
           WHERE logistics_id = ?
           ORDER BY event_time ASC""",
        (row["logistics_id"],),
    ).fetchall()
    events = [
        LogisticsEvent(
            event_id=e["event_id"],
            logistics_id=e["logistics_id"],
            event_time=e["event_time"],
            location=e["location"],
            event_status=e["event_status"],
            description=e["description"],
        )
        for e in event_rows
    ]

    return Logistics(
        logistics_id=row["logistics_id"],
        order_id=row["order_id"],
        current_status=row["current_status"],
        last_updated_at=row["last_updated_at"],
        estimated_delivery_at=row["estimated_delivery_at"],
        events=events,
    )


def list_all_with_logistics(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """供规则引擎批量扫描使用：一次查询拿到订单及其物流当前状态，
    避免对每条订单单独查询物流表导致的 N+1 问题。
    """
    return conn.execute(
        """SELECT o.*, l.current_status AS logistics_status,
                  l.last_updated_at AS logistics_last_updated_at,
                  l.estimated_delivery_at AS logistics_estimated_delivery_at
           FROM orders o
           LEFT JOIN logistics l ON l.order_id = o.order_id"""
    ).fetchall()
