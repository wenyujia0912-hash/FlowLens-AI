"""
异常与 AI 诊断数据访问层。

职责边界：仅做 SQL 读写。"是否应该生成异常"的判断属于 rule_engine；
"是否已存在活跃异常（去重）"的判断属于 anomaly_service，本模块只提供
它们需要的查询原语。
"""

from __future__ import annotations

import sqlite3

from models.schemas import AIDiagnosis, Anomaly


def _row_to_anomaly(row: sqlite3.Row) -> Anomaly:
    return Anomaly(
        anomaly_id=row["anomaly_id"],
        order_id=row["order_id"],
        anomaly_type=row["anomaly_type"],
        detected_at=row["detected_at"],
        rule_code=row["rule_code"],
        severity=row["severity"],
        status=row["status"],
        resolved_at=row["resolved_at"],
    )


def get_by_id(conn: sqlite3.Connection, anomaly_id: str) -> Anomaly | None:
    row = conn.execute(
        "SELECT * FROM anomalies WHERE anomaly_id = ?", (anomaly_id,)
    ).fetchone()
    return _row_to_anomaly(row) if row else None


def list_all(
    conn: sqlite3.Connection,
    *,
    anomaly_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    detected_from: str | None = None,
    detected_to: str | None = None,
) -> list[Anomaly]:
    """列出异常，支持按类型/风险等级/状态/发现时间筛选（产品需求 §5.4、
    页面交互设计 §3.4）。
    """
    clauses: list[str] = []
    params: list[str] = []

    if anomaly_type:
        clauses.append("anomaly_type = ?")
        params.append(anomaly_type)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if detected_from:
        clauses.append("detected_at >= ?")
        params.append(detected_from)
    if detected_to:
        clauses.append("detected_at <= ?")
        params.append(detected_to)

    sql = "SELECT * FROM anomalies"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    # 默认优先展示高风险和待确认（产品需求 §5.4 列表要求），具体排序规则：
    # 先按状态（待确认优先），再按风险等级（高优先），再按发现时间倒序。
    sql += """
        ORDER BY
            CASE status WHEN '待确认' THEN 0 ELSE 1 END,
            CASE severity WHEN '高' THEN 0 WHEN '中' THEN 1 ELSE 2 END,
            detected_at DESC
    """

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_anomaly(r) for r in rows]


def list_by_order(conn: sqlite3.Connection, order_id: str) -> list[Anomaly]:
    rows = conn.execute(
        "SELECT * FROM anomalies WHERE order_id = ? ORDER BY detected_at DESC",
        (order_id,),
    ).fetchall()
    return [_row_to_anomaly(r) for r in rows]


def find_active_by_order_and_rule(
    conn: sqlite3.Connection, order_id: str, rule_code: str, active_statuses: tuple[str, ...]
) -> Anomaly | None:
    """查找"同一订单、同一规则代码、处于活跃状态"的异常，供去重判断使用。

    技术方案 §5："同一订单同一规则在异常未关闭期间不应每次运行都重复创建
    新异常...例如订单编号+规则代码+活跃状态唯一。"
    """
    placeholders = ",".join("?" for _ in active_statuses)
    row = conn.execute(
        f"""SELECT * FROM anomalies
            WHERE order_id = ? AND rule_code = ? AND status IN ({placeholders})
            LIMIT 1""",
        (order_id, rule_code, *active_statuses),
    ).fetchone()
    return _row_to_anomaly(row) if row else None


def insert(conn: sqlite3.Connection, anomaly: Anomaly) -> None:
    conn.execute(
        """INSERT INTO anomalies
           (anomaly_id, order_id, anomaly_type, detected_at, rule_code, severity, status, resolved_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            anomaly.anomaly_id,
            anomaly.order_id,
            anomaly.anomaly_type,
            anomaly.detected_at,
            anomaly.rule_code,
            anomaly.severity,
            anomaly.status,
            anomaly.resolved_at,
        ),
    )


def update_severity(conn: sqlite3.Connection, anomaly_id: str, severity: str) -> None:
    """人工修改风险等级（产品需求 §5.4.1："风险等级可由人工修改并保存"）。"""
    conn.execute(
        "UPDATE anomalies SET severity = ? WHERE anomaly_id = ?", (severity, anomaly_id)
    )


def update_status(
    conn: sqlite3.Connection, anomaly_id: str, status: str, resolved_at: str | None = None
) -> None:
    """更新异常状态。异常关闭/解决必须是明确的人工动作或规则触发
    （产品需求 §5.5），本函数只负责执行更新，调用方（service 层）
    负责判断"什么时候该调用这个函数"。
    """
    conn.execute(
        "UPDATE anomalies SET status = ?, resolved_at = ? WHERE anomaly_id = ?",
        (status, resolved_at, anomaly_id),
    )


# --- AI 诊断记录（阶段 5 会用到，本阶段先提供数据访问原语） ---


def _row_to_diagnosis(row: sqlite3.Row) -> AIDiagnosis:
    return AIDiagnosis(
        diagnosis_id=row["diagnosis_id"],
        anomaly_id=row["anomaly_id"],
        generated_at=row["generated_at"],
        summary=row["summary"],
        causes_json=row["causes_json"],
        impact=row["impact"],
        risk_suggestion=row["risk_suggestion"],
        recommendations_json=row["recommendations_json"],
        communication_draft=row["communication_draft"],
        verification_json=row["verification_json"],
        model_type=row["model_type"],
    )


def insert_diagnosis(conn: sqlite3.Connection, diagnosis: AIDiagnosis) -> None:
    conn.execute(
        """INSERT INTO ai_diagnoses
           (diagnosis_id, anomaly_id, generated_at, summary, causes_json, impact,
            risk_suggestion, recommendations_json, communication_draft, verification_json, model_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            diagnosis.diagnosis_id,
            diagnosis.anomaly_id,
            diagnosis.generated_at,
            diagnosis.summary,
            diagnosis.causes_json,
            diagnosis.impact,
            diagnosis.risk_suggestion,
            diagnosis.recommendations_json,
            diagnosis.communication_draft,
            diagnosis.verification_json,
            diagnosis.model_type,
        ),
    )


def list_diagnoses_for_anomaly(conn: sqlite3.Connection, anomaly_id: str) -> list[AIDiagnosis]:
    """按生成时间倒序返回某异常的全部诊断记录（支持"重新分析"保留历史版本，
    对应阶段 0 H5 问题的默认处理方式：保留历史，不覆盖）。

    【本阶段测试中发现并修复的缺陷】generated_at 精度为秒，如果用户在同一秒内
    连续点击"重新分析"（完全可能发生，诊断生成本身很快），多条记录会有相同的
    generated_at，仅按它排序时顺序不确定（SQLite对相等排序键不保证稳定顺序），
    导致"最新一次诊断"可能排不到最前面。改为用 rowid 作为同秒内的决胜键——
    rowid 由 SQLite 按插入顺序自动分配，不受 diagnosis_id 文本主键影响。
    """
    rows = conn.execute(
        "SELECT *, rowid FROM ai_diagnoses WHERE anomaly_id = ? ORDER BY generated_at DESC, rowid DESC",
        (anomaly_id,),
    ).fetchall()
    return [_row_to_diagnosis(r) for r in rows]
