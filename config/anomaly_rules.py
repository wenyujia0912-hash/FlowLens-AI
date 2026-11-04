"""
异常规则阈值集中配置。

技术方案 §5 要求："规则阈值应集中配置，便于修改和测试。"
本文件仅存放阈值等配置数据，不包含规则判断逻辑——判断逻辑将在阶段 3
的 services/rule_engine.py（或 anomaly_service.py）中实现，依赖本文件的值。

当前阶段（阶段 1：项目骨架）只搭建占位结构，具体数值为默认建议值，
待阶段 3 实现规则引擎时需与用户确认后再最终定稿（见阶段 0 产出的
H2 歧义问题：物流停滞阈值、供应商备货阈值、状态冲突组合清单）。
"""

from __future__ import annotations

# 规则代码常量，与数据库 anomalies.rule_code 字段取值保持一致。
RULE_SHIP_OVERDUE = "SHIP_OVERDUE"
RULE_DELIVERY_STALLED = "DELIVERY_STALLED"
RULE_DELIVERY_OVERDUE = "DELIVERY_OVERDUE"
RULE_SUPPLIER_PREP_DELAY = "SUPPLIER_PREP_DELAY"
RULE_STATUS_CONFLICT = "STATUS_CONFLICT"

ALL_RULE_CODES = (
    RULE_SHIP_OVERDUE,
    RULE_DELIVERY_STALLED,
    RULE_DELIVERY_OVERDUE,
    RULE_SUPPLIER_PREP_DELAY,
    RULE_STATUS_CONFLICT,
)

# --- 阈值配置（默认建议值，阶段 3 实现规则引擎前需与用户确认） ---

# 物流最后更新时间超过该小时数，且未签收，判定为"物流停滞/延迟"。
DELIVERY_STALLED_HOURS: int = 48

# 供应商备货状态更新时间超过该小时数，判定为"供应商备货异常"。
SUPPLIER_PREP_DELAY_HOURS: int = 72

# 订单状态 × 物流状态的预定义不合理组合清单。
# 当前为占位示例，具体清单需在阶段 3 实现前与用户确认完整列表（阶段 0 的 H2 问题）。
# 格式：(订单状态, 物流状态) 二元组。
STATUS_CONFLICT_PAIRS: tuple[tuple[str, str], ...] = (
    ("已取消", "运输中"),
    ("已取消", "派送中"),
    ("已取消", "已签收"),
    ("待确认", "运输中"),
    ("待确认", "已签收"),
)

# 同一订单、同一规则代码在"活跃"（未关闭/未误报）期间的去重判定使用的
# 异常状态集合——命中这些状态时视为"该规则已有活跃异常，不应重复创建"。
ACTIVE_ANOMALY_STATUSES: tuple[str, ...] = ("待确认", "处理中")
