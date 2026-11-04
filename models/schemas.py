"""
跨层共用的数据结构定义。

目的：repositories 层返回 dataclass 而非裸 sqlite3.Row/dict，让 services 层
和未来的 pages 层之间有一份清晰的契约，减少"某个字段到底叫什么"的隐性耦合。

本文件只定义结构，不包含任何业务逻辑或数据库访问代码。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Customer:
    customer_id: str
    name: str
    industry: str
    tier: str
    status: str
    created_at: str


@dataclass
class Supplier:
    supplier_id: str
    name: str
    category: str
    status: str
    lead_time_days: int


@dataclass
class OrderItem:
    item_id: str
    order_id: str
    product_name: str
    quantity: int
    unit_price: float


@dataclass
class LogisticsEvent:
    event_id: str
    logistics_id: str
    event_time: str
    location: str
    event_status: str
    description: str | None


@dataclass
class Logistics:
    logistics_id: str
    order_id: str
    current_status: str
    last_updated_at: str
    estimated_delivery_at: str
    events: list[LogisticsEvent] = field(default_factory=list)


@dataclass
class Order:
    order_id: str
    customer_id: str
    supplier_id: str
    order_date: str
    amount: float
    status: str
    expected_ship_at: str
    shipped_at: str | None
    expected_delivery_at: str
    delivered_at: str | None
    supplier_prep_status: str
    supplier_prep_updated_at: str


@dataclass
class OrderDetail:
    """订单详情聚合结构，对应页面交互设计 §3.3 的订单详情页需求
    （订单摘要 + 商品明细 + 履约时间线 + 供应商信息 + 物流节点 + 关联异常）。
    """

    order: Order
    customer: Customer
    supplier: Supplier
    items: list[OrderItem] = field(default_factory=list)
    logistics: Logistics | None = None
    anomaly_ids: list[str] = field(default_factory=list)


@dataclass
class Anomaly:
    anomaly_id: str
    order_id: str
    anomaly_type: str
    detected_at: str
    rule_code: str
    severity: str
    status: str
    resolved_at: str | None


@dataclass
class AIDiagnosis:
    diagnosis_id: str
    anomaly_id: str
    generated_at: str
    summary: str
    causes_json: str
    impact: str
    risk_suggestion: str
    recommendations_json: str
    communication_draft: str
    verification_json: str
    model_type: str


@dataclass
class OperationTask:
    task_id: str
    anomaly_id: str | None
    order_id: str | None
    title: str
    description: str | None
    priority: str
    assignee: str
    due_at: str
    status: str
    result: str | None
    created_at: str
    completed_at: str | None


@dataclass
class TaskLog:
    log_id: str
    task_id: str
    action: str
    content: str | None
    created_at: str
    actor: str


@dataclass
class RuleViolation:
    """规则引擎的判断输出：一条"应该生成异常"的结论，连带可复核的依据。

    不直接等同于数据库里的 Anomaly 记录——由 anomaly_service 决定是否真正
    写入（取决于去重判断）。evidence 字段记录触发该规则所依据的具体字段值，
    确保异常的可追溯性（产品需求 §5.4.2："AI结果必须能追溯到输入的...字段
    或触发规则"，此处是规则引擎层面的对应实现，为后续 AI 诊断提供可引用的
    事实依据）。
    """

    order_id: str
    rule_code: str
    anomaly_type: str
    severity: str
    evidence: dict[str, str]
