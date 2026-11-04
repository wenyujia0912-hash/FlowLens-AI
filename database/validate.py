"""
数据完整性校验脚本。

对应技术方案 §4（数据完整性与业务约束）、§7（"数据生成后执行完整性检查：
外键、时间先后、状态组合、金额计算"）。

本脚本在 schema.sql 的 CHECK 约束之外，补充两类检查：
    1. SQLite 的 CHECK 约束只在 INSERT/UPDATE 时触发，本脚本额外做一次
       全表扫描复核，确认约束确实生效、没有通过其他路径绕过。
    2. 跨表关系的完整性（例如"已签收订单必须有合理的物流签收事件"），
       这类检查涉及多表 JOIN，不适合写进单表的 CHECK 约束。

运行方式：
    python -m database.validate
    或 python database/validate.py
"""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_config  # noqa: E402


@dataclass
class ValidationReport:
    checks_run: int = 0
    checks_passed: int = 0
    failures: list[str] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks_run += 1
        if ok:
            self.checks_passed += 1
        else:
            self.failures.append(f"{name}: {detail}")

    @property
    def all_passed(self) -> bool:
        return not self.failures


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    return conn.execute(sql).fetchone()[0]


def validate(conn: sqlite3.Connection) -> ValidationReport:
    report = ValidationReport()

    # --- 外键完整性：orders.customer_id / supplier_id 必须存在 ---
    orphan_customer = _scalar(
        conn,
        """SELECT COUNT(*) FROM orders o
           LEFT JOIN customers c ON o.customer_id = c.customer_id
           WHERE c.customer_id IS NULL""",
    )
    report.record("订单客户外键完整性", orphan_customer == 0, f"{orphan_customer} 条订单的客户不存在")

    orphan_supplier = _scalar(
        conn,
        """SELECT COUNT(*) FROM orders o
           LEFT JOIN suppliers s ON o.supplier_id = s.supplier_id
           WHERE s.supplier_id IS NULL""",
    )
    report.record("订单供应商外键完整性", orphan_supplier == 0, f"{orphan_supplier} 条订单的供应商不存在")

    orphan_items = _scalar(
        conn,
        """SELECT COUNT(*) FROM order_items oi
           LEFT JOIN orders o ON oi.order_id = o.order_id
           WHERE o.order_id IS NULL""",
    )
    report.record("商品明细外键完整性", orphan_items == 0, f"{orphan_items} 条商品明细的订单不存在")

    orphan_logistics_events = _scalar(
        conn,
        """SELECT COUNT(*) FROM logistics_events le
           LEFT JOIN logistics l ON le.logistics_id = l.logistics_id
           WHERE l.logistics_id IS NULL""",
    )
    report.record("物流节点外键完整性", orphan_logistics_events == 0, f"{orphan_logistics_events} 条物流节点的物流记录不存在")

    orphan_anomalies = _scalar(
        conn,
        """SELECT COUNT(*) FROM anomalies a
           LEFT JOIN orders o ON a.order_id = o.order_id
           WHERE o.order_id IS NULL""",
    )
    report.record("异常记录外键完整性", orphan_anomalies == 0, f"{orphan_anomalies} 条异常的订单不存在")

    # --- 金额/数量非负 ---
    negative_amount = _scalar(conn, "SELECT COUNT(*) FROM orders WHERE amount < 0")
    report.record("订单金额非负", negative_amount == 0, f"{negative_amount} 条订单金额为负")

    negative_qty_or_price = _scalar(
        conn, "SELECT COUNT(*) FROM order_items WHERE quantity <= 0 OR unit_price < 0"
    )
    report.record("商品数量/单价合法", negative_qty_or_price == 0, f"{negative_qty_or_price} 条商品明细数量非正或单价为负")

    # --- 时间先后关系 ---
    bad_ship_order = _scalar(
        conn, "SELECT COUNT(*) FROM orders WHERE shipped_at IS NOT NULL AND shipped_at < order_date"
    )
    report.record("发货时间不早于下单时间", bad_ship_order == 0, f"{bad_ship_order} 条订单发货早于下单")

    bad_deliver_ship = _scalar(
        conn,
        """SELECT COUNT(*) FROM orders
           WHERE delivered_at IS NOT NULL AND (shipped_at IS NULL OR delivered_at < shipped_at)""",
    )
    report.record("签收时间不早于发货时间", bad_deliver_ship == 0, f"{bad_deliver_ship} 条订单签收早于发货或缺少发货时间")

    # --- 已签收订单必须有合理的物流签收事件；未签收订单不应有实际签收时间 ---
    delivered_without_logistics = _scalar(
        conn,
        """SELECT COUNT(*) FROM orders o
           WHERE o.status = '已签收'
             AND NOT EXISTS (
                 SELECT 1 FROM logistics l WHERE l.order_id = o.order_id AND l.current_status = '已签收'
             )""",
    )
    report.record(
        "已签收订单有对应物流签收记录",
        delivered_without_logistics == 0,
        f"{delivered_without_logistics} 条已签收订单缺少对应的物流签收记录",
    )

    not_delivered_with_time = _scalar(
        conn, "SELECT COUNT(*) FROM orders WHERE status != '已签收' AND delivered_at IS NOT NULL"
    )
    report.record(
        "未签收订单不应有实际签收时间",
        not_delivered_with_time == 0,
        f"{not_delivered_with_time} 条未签收订单却有实际签收时间",
    )

    # --- 已完成任务必须有完成时间和处理结果 ---
    # 阶段 2 尚未生成任务数据，此检查在任务表为空时应直接通过（0 条违规）。
    completed_task_table_exists = _scalar(
        conn, "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='operation_tasks'"
    )
    if completed_task_table_exists:
        bad_completed_tasks = _scalar(
            conn,
            """SELECT COUNT(*) FROM operation_tasks
               WHERE status = '已完成' AND (result IS NULL OR completed_at IS NULL)""",
        )
        report.record(
            "已完成任务有完成时间和处理结果",
            bad_completed_tasks == 0,
            f"{bad_completed_tasks} 条已完成任务缺少结果或完成时间",
        )

    # --- 异常去重：同一订单同一规则在活跃状态下不应有多条 ---
    dup_active_anomalies = _scalar(
        conn,
        """SELECT COUNT(*) FROM (
               SELECT order_id, rule_code, COUNT(*) AS c
               FROM anomalies
               WHERE status IN ('待确认', '处理中')
               GROUP BY order_id, rule_code
               HAVING c > 1
           )""",
    )
    report.record(
        "同订单同规则活跃异常不重复",
        dup_active_anomalies == 0,
        f"{dup_active_anomalies} 组订单+规则在活跃状态下存在重复异常",
    )

    return report


def main() -> int:
    config = get_config()
    if not config.database_path.exists():
        print(f"[validate] 数据库文件不存在: {config.database_path}", file=sys.stderr)
        print("[validate] 请先运行 python -m database.seed_data 生成数据。", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(config.database_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        report = validate(conn)
    finally:
        conn.close()

    print(f"[validate] 共执行 {report.checks_run} 项检查，通过 {report.checks_passed} 项")
    if report.all_passed:
        print("[validate] 全部检查通过。")
        return 0

    print("[validate] 以下检查未通过：")
    for failure in report.failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
