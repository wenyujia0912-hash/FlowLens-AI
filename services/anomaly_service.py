"""
异常业务服务。

职责边界：
    - 调用 rule_engine 做确定性判断（本模块不重复实现任何判断逻辑）。
    - 调用 anomaly_repository 做去重检查和持久化。
    - 异常状态的人工变更（采纳风险等级修改、关闭/误报标记）在此提供入口，
      但"什么情况下应该关闭异常"由调用方（未来的页面/用户操作）决定，
      本模块不会自作主张地自动关闭异常——产品需求 §5.5 明确要求
      "异常关闭应有明确人工动作或规则"。
    - 本模块不包含任何 AI 调用（阶段 5 才引入 ai_service.py）。
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime

from config.anomaly_rules import ACTIVE_ANOMALY_STATUSES
from models.schemas import AIDiagnosis, Anomaly, RuleViolation
from repositories import anomaly_repository, order_repository
from services import ai_service, rule_engine


def _new_anomaly_id() -> str:
    """生成异常编号。

    【本阶段测试中发现并修复的缺陷】最初实现使用 order_id+rule_code+时间
    做哈希派生 ID，意图是"同一次扫描内幂等"，但副作用是：同一订单同一
    规则在不同次扫描之间如果时间戳相同（例如测试中用固定 now），会生成
    完全相同的 ID，导致"先关闭旧异常、再扫描出新异常"场景下插入时触发
    anomaly_id 的 UNIQUE 约束冲突——这是真实的业务场景（异常关闭后同一
    问题复发，理应创建新记录），不能被 ID 生成方式误伤。
    改为随机 UUID，异常记录的唯一性只应该由"是否为新记录"决定，不应该
    与判断内容耦合。去重仍完全由 find_active_by_order_and_rule 负责。
    """
    return f"ANOM-{uuid.uuid4().hex[:10].upper()}"


def scan_and_create_anomalies(
    conn: sqlite3.Connection, now: datetime | None = None
) -> dict:
    """扫描全部订单，运行规则引擎，对命中且未被去重的违规创建异常记录。

    返回统计结果：{"scanned": N, "violations_found": N, "created": N, "skipped_duplicate": N}

    去重策略（技术方案 §5）："订单编号+规则代码+活跃状态唯一"——如果该
    订单该规则已存在状态为 待确认/处理中 的异常，则跳过，不创建新记录。
    """
    now = now or datetime.now()
    order_rows = order_repository.list_all_with_logistics(conn)
    violations: list[RuleViolation] = rule_engine.scan_orders(order_rows, now)

    created = 0
    skipped_duplicate = 0

    for violation in violations:
        existing = anomaly_repository.find_active_by_order_and_rule(
            conn, violation.order_id, violation.rule_code, ACTIVE_ANOMALY_STATUSES
        )
        if existing is not None:
            skipped_duplicate += 1
            continue

        anomaly_id = _new_anomaly_id()
        anomaly = Anomaly(
            anomaly_id=anomaly_id,
            order_id=violation.order_id,
            anomaly_type=violation.anomaly_type,
            detected_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
            rule_code=violation.rule_code,
            severity=violation.severity,
            status="待确认",
            resolved_at=None,
        )
        anomaly_repository.insert(conn, anomaly)
        created += 1

    return {
        "scanned": len(order_rows),
        "violations_found": len(violations),
        "created": created,
        "skipped_duplicate": skipped_duplicate,
    }


def get_anomaly_evidence(order_row) -> list[RuleViolation]:
    """为异常详情页提供"重新计算一遍规则判断依据"的能力，用于展示
    触发规则和关键事实（产品需求 §5.4.1）。与 scan_and_create_anomalies
    共用同一套 rule_engine 判断函数，保证展示的依据与实际触发逻辑一致。
    """
    return rule_engine.check_order(order_row)


def update_severity(conn: sqlite3.Connection, anomaly_id: str, severity: str) -> None:
    """人工修改风险等级（产品需求 §5.4.1）。"""
    if severity not in ("高", "中", "低"):
        raise ValueError(f"不合法的风险等级: {severity}")
    anomaly_repository.update_severity(conn, anomaly_id, severity)


def mark_resolved(conn: sqlite3.Connection, anomaly_id: str, now: datetime | None = None) -> None:
    """人工标记异常为"已解决"。这是明确的人工动作（产品需求 §5.5 要求），
    不会被任务完成等其他操作自动触发。
    """
    now = now or datetime.now()
    anomaly_repository.update_status(
        conn, anomaly_id, status="已解决", resolved_at=now.strftime("%Y-%m-%dT%H:%M:%S")
    )


def mark_closed(conn: sqlite3.Connection, anomaly_id: str, now: datetime | None = None) -> None:
    """人工标记异常为"已关闭"。"""
    now = now or datetime.now()
    anomaly_repository.update_status(
        conn, anomaly_id, status="已关闭", resolved_at=now.strftime("%Y-%m-%dT%H:%M:%S")
    )


def mark_false_positive(conn: sqlite3.Connection, anomaly_id: str, now: datetime | None = None) -> None:
    """人工标记异常为"误报"（产品需求 §6 状态定义表）。"""
    now = now or datetime.now()
    anomaly_repository.update_status(
        conn, anomaly_id, status="误报", resolved_at=now.strftime("%Y-%m-%dT%H:%M:%S")
    )


def mark_in_progress(conn: sqlite3.Connection, anomaly_id: str) -> None:
    """标记异常进入处理中状态（例如已创建关联任务后）。"""
    anomaly_repository.update_status(conn, anomaly_id, status="处理中", resolved_at=None)


# ----------------------------------------------------------------------
# AI 诊断（阶段5新增）
# ----------------------------------------------------------------------


def _new_diagnosis_id() -> str:
    return f"DIAG-{uuid.uuid4().hex[:10].upper()}"


def run_diagnosis(conn: sqlite3.Connection, anomaly_id: str) -> AIDiagnosis:
    """对指定异常运行AI诊断（当前为Mock），并持久化诊断记录。

    流程（严格遵循产品需求§5.4.1和技术方案§6）：
        1. 读取异常记录，取得订单ID和规则代码。
        2. 重新查询该订单的完整数据（含物流JOIN），
           重新运行 rule_engine 得到该规则对应的 RuleViolation
           （evidence 字段，保证AI看到的"事实依据"与异常触发时完全一致）。
        3. 调用 ai_service.diagnose_anomaly() 生成诊断结果（Mock）。
        4. 诊断结果存入 ai_diagnoses 表，**不修改** anomalies/orders 的
           任何状态字段——诊断只是"生成建议"，不是"执行操作"。
        5. 支持"重新分析"：每次调用都插入一条新记录，不覆盖历史版本
           （阶段0的H5歧义问题，本阶段采用"保留全部历史"的默认处理）。

    异常:
        ValueError: 异常不存在，或该异常对应的订单找不到对应规则的
            判断依据（例如订单数据已变化、不再满足触发条件）。
        ai_service.DiagnosisError: Mock诊断本身的校验失败（理论上不会
            发生，因为Mock模板是我们自己维护的，但调用方应当能处理
            这个异常，为未来接入真实模型做好准备）。
    """
    anomaly = anomaly_repository.get_by_id(conn, anomaly_id)
    if anomaly is None:
        raise ValueError(f"异常不存在: {anomaly_id}")

    order_rows = order_repository.list_all_with_logistics(conn)
    order_row = next((r for r in order_rows if r["order_id"] == anomaly.order_id), None)
    if order_row is None:
        raise ValueError(f"异常 {anomaly_id} 关联的订单 {anomaly.order_id} 不存在")

    all_violations = rule_engine.check_order(order_row)
    violation = next((v for v in all_violations if v.rule_code == anomaly.rule_code), None)
    if violation is None:
        # 订单数据可能已经变化（例如已经补发货），不再满足原规则条件。
        # 仍然允许诊断，但用异常记录本身的信息构造一个"退化"的依据对象，
        # 并在摘要里不会假装这是"当前仍然成立"的事实——这里选择直接报错，
        # 让用户知道"这条异常对应的触发条件，在当前数据下已经不存在了"，
        # 而不是生成一份基于过时事实的诊断。
        raise ValueError(
            f"订单 {anomaly.order_id} 当前数据已不满足规则 {anomaly.rule_code} 的触发条件，"
            "可能已被处理。建议人工核实后决定是否关闭该异常，而非继续诊断。"
        )

    result = ai_service.diagnose_anomaly(violation)

    diagnosis = AIDiagnosis(
        diagnosis_id=_new_diagnosis_id(),
        anomaly_id=anomaly_id,
        **result.to_json_fields(),
    )
    anomaly_repository.insert_diagnosis(conn, diagnosis)
    return diagnosis


def get_diagnosis_history(conn: sqlite3.Connection, anomaly_id: str) -> list[AIDiagnosis]:
    """返回某异常的全部诊断历史（按生成时间倒序，最新的在前）。"""
    return anomaly_repository.list_diagnoses_for_anomaly(conn, anomaly_id)
