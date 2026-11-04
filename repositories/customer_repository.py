"""
客户数据访问层。

职责边界：本模块只做 SQL 读写，不包含任何业务判断（例如"客户是否算重点
客户"之类的规则属于 service 层或数据本身，不在这里做二次解释）。
"""

from __future__ import annotations

import sqlite3

from models.schemas import Customer


def _row_to_customer(row: sqlite3.Row) -> Customer:
    return Customer(
        customer_id=row["customer_id"],
        name=row["name"],
        industry=row["industry"],
        tier=row["tier"],
        status=row["status"],
        created_at=row["created_at"],
    )


def get_by_id(conn: sqlite3.Connection, customer_id: str) -> Customer | None:
    row = conn.execute(
        "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    return _row_to_customer(row) if row else None


def list_all(
    conn: sqlite3.Connection,
    *,
    name_contains: str | None = None,
    industry: str | None = None,
    tier: str | None = None,
    status: str | None = None,
) -> list[Customer]:
    """列出客户，支持按名称模糊搜索和行业/等级/状态筛选。

    对应产品需求 §5.2："支持按客户名称搜索，按行业、等级、状态筛选。"
    """
    clauses: list[str] = []
    params: list[str] = []

    if name_contains:
        clauses.append("name LIKE ?")
        params.append(f"%{name_contains}%")
    if industry:
        clauses.append("industry = ?")
        params.append(industry)
    if tier:
        clauses.append("tier = ?")
        params.append(tier)
    if status:
        clauses.append("status = ?")
        params.append(status)

    sql = "SELECT * FROM customers"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC"

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_customer(r) for r in rows]


def count_orders_for_customer(conn: sqlite3.Connection, customer_id: str) -> int:
    """客户关联的订单数量——必须由数据库关联数据计算（产品需求 §5.2 的硬性要求），
    不得在上层缓存为静态数字。
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM orders WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    return row["n"]


def sum_order_amount_for_customer(conn: sqlite3.Connection, customer_id: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total FROM orders WHERE customer_id = ?",
        (customer_id,),
    ).fetchone()
    return float(row["total"])


def count_anomalies_for_customer(conn: sqlite3.Connection, customer_id: str) -> int:
    """客户关联的异常订单数量——同样要求实时关联计算（产品需求 §5.2）。"""
    row = conn.execute(
        """SELECT COUNT(DISTINCT a.anomaly_id) AS n
           FROM anomalies a
           JOIN orders o ON a.order_id = o.order_id
           WHERE o.customer_id = ?""",
        (customer_id,),
    ).fetchone()
    return row["n"]
