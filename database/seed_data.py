"""
模拟数据生成脚本。

对应技术方案 §7（数据生成策略）、§4（数据完整性约束）。

设计要点：
    - 固定随机种子（SEED = 20240101）控制随机性（客户/供应商/订单的具体
      内容每次生成完全一致）；但【阶段6修复后】时间基准 NOW 改为相对
      "脚本运行当天"动态计算，不再是写死的绝对日期——原因见下方
      `_reference_now()` 的说明：固定绝对日期会导致种子数据随真实时间
      推移"变旧"，使异常中心的"扫描新异常"功能（用真实当前时间判断）
      把大量正常订单误判为异常。
      因此"可复现"现在的含义是：同一天内多次生成的内容完全一致、
      且订单相对NOW的新旧关系（例如"5天前""48小时前超时"）永远正确，
      而不是"任何时候生成都得到逐字节相同的数据库"。
    - 不依赖 pandas / faker 等第三方库——当前网络环境无法安装，
      本脚本只用标准库 (random / datetime / sqlite3)。
      待网络恢复、用户确认后，可选择引入 Faker 让姓名/行业文案更丰富，
      但不是必需依赖，当前用内置的候选词列表拼接即可满足"虚构数据"要求。
    - 所有客户/供应商/商品名称均为虚构词汇拼接，不映射任何真实企业。
    - 重复运行安全：先检测是否已有数据，默认跳过；传 --force 才清空重建。

数据规模（技术方案 §7 建议值，第一批固定为建议区间的中间值，便于开发阶段
性能可控，正式演示前可调整）：
    - 客户：40 家（建议 30–50）
    - 供应商：15 家（建议 10–20）
    - 订单：400 条（建议 300–500）

异常正反例构造策略（阶段 0 产出的 H2/H7 问题的默认假设，待确认）：
    - 异常订单占比默认约 22%（文档未给出具体比例，此为本脚本的默认假设）。
    - 每种规则类型（SHIP_OVERDUE / DELIVERY_STALLED / DELIVERY_OVERDUE /
      SUPPLIER_PREP_DELAY / STATUS_CONFLICT）至少各构造若干正例和反例，
      反例指"数据形态接近触发条件但实际不应触发"的边界情况，用于阶段3
      规则引擎的测试样本。
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# 允许脚本既可以 `python database/seed_data.py` 直接运行，
# 也可以 `python -m database.seed_data` 以模块方式运行。
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import get_config  # noqa: E402
from config.anomaly_rules import (  # noqa: E402
    RULE_SHIP_OVERDUE,
    RULE_DELIVERY_STALLED,
    RULE_DELIVERY_OVERDUE,
    RULE_SUPPLIER_PREP_DELAY,
    RULE_STATUS_CONFLICT,
    DELIVERY_STALLED_HOURS,
    SUPPLIER_PREP_DELAY_HOURS,
    STATUS_CONFLICT_PAIRS,
)

SEED = 20240101

CUSTOMER_COUNT = 40
SUPPLIER_COUNT = 15
NORMAL_ORDER_COUNT = 310  # 正常订单（不含下方异常正反例订单）
ANOMALY_CASE_MULTIPLIER = 3  # 每种规则构造的正例/反例订单数

def _reference_now() -> datetime:
    """种子数据的"当前时间"基准。

    【阶段6修复】此前固定为 datetime(2024, 3, 20, 10, 0, 0)，随着真实挂钟
    时间推进，种子订单相对"今天"会越来越"久远"——异常中心的"扫描新异常"
    按钮默认用 datetime.now() 做判断，会把大量"只是时间久远"的正常订单
    误判为触发 SHIP_OVERDUE/DELIVERY_STALLED 等规则（这些规则本身就是
    "超过某个时间点"的判断，种子数据越老就越容易被误触发）。

    改为"运行种子脚本那一刻的时间，但把小时/分钟/秒对齐到固定值"：
        - 仍然对同一次运行内的全部计算使用同一个基准时间（内部一致）。
        - 不同天运行会得到不同的 NOW，但所有订单的时间字段都是相对这个
          NOW 偏移计算的（例如"5天前""48小时前"），所以生成出来的数据
          相对NOW的"新旧关系"永远不变——异常订单相对NOW仍然是异常，
          正常订单相对NOW仍然是正常，不会因为种子脚本是哪天跑的而改变
          这一相对关系的正确性。
        - 唯一不再保证的是"infinite future reproducibility"：今天生成
          和明天生成，绝对时间戳会不同（这是必要代价，用来保证"扫描
          新异常"按钮默认用真实当前时间判断时结果仍然正确）。
    """
    now = datetime.now()
    return now.replace(hour=10, minute=0, second=0, microsecond=0)


NOW = _reference_now()  # 相对"运行种子脚本时的今天"计算，而非写死的绝对日期

# --- 虚构词汇素材（均为拼接生成，不对应任何真实企业/个人） ---

_INDUSTRY_WORDS = (
    "智能制造", "快消零售", "医疗器械", "新能源", "跨境电商",
    "办公文具", "家居建材", "数码配件", "食品饮料", "美妆个护",
)
_CUSTOMER_SUFFIX = ("贸易有限公司", "供应链科技有限公司", "实业集团", "商贸有限公司", "采购中心")
_CUSTOMER_PREFIX = (
    "晨曦", "蓝海", "恒远", "汇众", "星链", "瀚宇", "锦程", "弘昌",
    "泰和", "聚力", "明德", "致远", "博雅", "泽信", "源达", "天际",
)

_SUPPLIER_SUFFIX = ("制造有限公司", "供应链有限公司", "工贸有限公司", "物资有限公司")
_SUPPLIER_PREFIX = (
    "恒昌", "顺达", "正源", "鸿运", "锐驰", "金诚", "合力", "广拓",
    "信和", "卓越", "创新", "联亿",
)

_PRODUCT_WORDS = (
    "智能传感器模块", "工业连接器", "包装纸箱", "办公座椅", "LED 灯具",
    "塑料周转箱", "标准螺丝组件", "保温包装材料", "电子元件托盘", "标签打印耗材",
)

_TIERS = ("战略客户", "重点客户", "普通客户")
_CUSTOMER_STATUSES = ("合作中", "合作中", "合作中", "暂停合作")  # 多数合作中
_SUPPLIER_CATEGORIES = ("原材料", "标准件", "包装物料", "电子元件", "五金配件")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _new_id(prefix: str, rng: random.Random) -> str:
    """生成稳定格式的业务编号：前缀 + 8 位十六进制，不使用自增整数，
    避免暴露"第几条记录"的实现细节，也便于未来迁移到分布式环境。
    """
    return f"{prefix}-{uuid.UUID(int=rng.getrandbits(128)).hex[:8].upper()}"


class SeedGenerator:
    """封装带状态的生成过程，所有随机性均来自同一个 random.Random 实例，
    保证整体生成过程在固定种子下完全可复现。
    """

    def __init__(self, seed: int = SEED) -> None:
        self.rng = random.Random(seed)
        self.customers: list[dict] = []
        self.suppliers: list[dict] = []
        self.orders: list[dict] = []
        self.order_items: list[dict] = []
        self.logistics: list[dict] = []
        self.logistics_events: list[dict] = []
        self.anomalies: list[dict] = []

    # ------------------------------------------------------------------
    # 客户与供应商
    # ------------------------------------------------------------------

    def generate_customers(self, count: int) -> None:
        used_names: set[str] = set()
        for _ in range(count):
            while True:
                name = (
                    self.rng.choice(_CUSTOMER_PREFIX)
                    + self.rng.choice(_INDUSTRY_WORDS)[:2]
                    + self.rng.choice(_CUSTOMER_SUFFIX)
                )
                if name not in used_names:
                    used_names.add(name)
                    break
            created_at = NOW - timedelta(days=self.rng.randint(30, 900))
            self.customers.append(
                {
                    "customer_id": _new_id("CUST", self.rng),
                    "name": name,
                    "industry": self.rng.choice(_INDUSTRY_WORDS),
                    "tier": self.rng.choice(_TIERS),
                    "status": self.rng.choice(_CUSTOMER_STATUSES),
                    "created_at": _iso(created_at),
                }
            )

    def generate_suppliers(self, count: int) -> None:
        used_names: set[str] = set()
        for _ in range(count):
            while True:
                name = (
                    self.rng.choice(_SUPPLIER_PREFIX)
                    + self.rng.choice(_SUPPLIER_SUFFIX)
                )
                if name not in used_names:
                    used_names.add(name)
                    break
            self.suppliers.append(
                {
                    "supplier_id": _new_id("SUPP", self.rng),
                    "name": name,
                    "category": self.rng.choice(_SUPPLIER_CATEGORIES),
                    "status": "合作中" if self.rng.random() > 0.1 else "暂停合作",
                    "lead_time_days": self.rng.randint(2, 20),
                }
            )

    # ------------------------------------------------------------------
    # 订单基础结构（正常订单 + 异常正反例的共用构造逻辑）
    # ------------------------------------------------------------------

    def _build_base_order(
        self,
        order_date: datetime,
        status: str,
        expected_ship_days: int,
        expected_delivery_days: int,
    ) -> dict:
        customer = self.rng.choice(self.customers)
        supplier = self.rng.choice(self.suppliers)
        amount = round(self.rng.uniform(1500, 180000), 2)
        order = {
            "order_id": _new_id("ORD", self.rng),
            "customer_id": customer["customer_id"],
            "supplier_id": supplier["supplier_id"],
            "order_date": _iso(order_date),
            "amount": amount,
            "status": status,
            "expected_ship_at": _iso(order_date + timedelta(days=expected_ship_days)),
            "shipped_at": None,
            "expected_delivery_at": _iso(order_date + timedelta(days=expected_delivery_days)),
            "delivered_at": None,
            "supplier_prep_status": "备货完成",
            "supplier_prep_updated_at": _iso(order_date + timedelta(hours=self.rng.randint(4, 36))),
        }
        return order

    def _add_order_items(self, order: dict) -> None:
        for _ in range(self.rng.randint(1, 4)):
            self.order_items.append(
                {
                    "item_id": _new_id("ITEM", self.rng),
                    "order_id": order["order_id"],
                    "product_name": self.rng.choice(_PRODUCT_WORDS),
                    "quantity": self.rng.randint(1, 200),
                    "unit_price": round(self.rng.uniform(5, 2000), 2),
                }
            )

    def _add_logistics(
        self,
        order: dict,
        current_status: str,
        last_updated_at: datetime,
        estimated_delivery_at: datetime,
        event_count: int = 2,
    ) -> dict:
        logi = {
            "logistics_id": _new_id("LOGI", self.rng),
            "order_id": order["order_id"],
            "current_status": current_status,
            "last_updated_at": _iso(last_updated_at),
            "estimated_delivery_at": _iso(estimated_delivery_at),
        }
        self.logistics.append(logi)

        event_statuses = ["已揽收", "运输中", "到达分拨中心", "派送中", "已签收"]
        chosen = event_statuses[: max(1, event_count)]
        base_time = order["shipped_at"] or order["order_date"]
        base_dt = datetime.strptime(base_time, "%Y-%m-%dT%H:%M:%S")
        for i, ev_status in enumerate(chosen):
            self.logistics_events.append(
                {
                    "event_id": _new_id("EVT", self.rng),
                    "logistics_id": logi["logistics_id"],
                    "event_time": _iso(base_dt + timedelta(hours=self.rng.randint(1, 12) * (i + 1))),
                    "location": self.rng.choice(("上海转运中心", "广州分拨点", "武汉中转仓", "成都配送站", "北京集散中心")),
                    "event_status": ev_status,
                    "description": f"{ev_status}（模拟物流节点）",
                }
            )
        return logi

    # ------------------------------------------------------------------
    # 正常订单（已签收且各时间关系合理，不触发任何规则）
    # ------------------------------------------------------------------

    def generate_normal_orders(self, count: int) -> None:
        for _ in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(10, 400))
            order = self._build_base_order(
                order_date,
                status="已签收",
                expected_ship_days=self.rng.randint(1, 4),
                expected_delivery_days=self.rng.randint(5, 12),
            )
            # 实际发货/签收时间均略早于或接近预计时间，保证不触发
            # DELIVERY_OVERDUE/SHIP_OVERDUE。
            expected_ship = datetime.strptime(order["expected_ship_at"], "%Y-%m-%dT%H:%M:%S")
            shipped_at = expected_ship - timedelta(hours=self.rng.randint(1, 20))
            expected_delivery = datetime.strptime(order["expected_delivery_at"], "%Y-%m-%dT%H:%M:%S")
            delivered_at = expected_delivery - timedelta(hours=self.rng.randint(2, 30))

            order["shipped_at"] = _iso(shipped_at)
            order["delivered_at"] = _iso(delivered_at)

            self.orders.append(order)
            self._add_order_items(order)
            self._add_logistics(
                order,
                current_status="已签收",
                last_updated_at=delivered_at,
                estimated_delivery_at=expected_delivery,
                event_count=self.rng.randint(3, 5),
            )

    # ------------------------------------------------------------------
    # 异常正反例：每种规则独立构造
    # ------------------------------------------------------------------

    def generate_ship_overdue_cases(self, count: int) -> None:
        """SHIP_OVERDUE 正例：now > expected_ship_at 且未发货且订单未取消。
        反例：预计发货时间已过但实际上已经发货（不应触发）。
        """
        for i in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(5, 15))
            is_positive = i % 2 == 0
            order = self._build_base_order(
                order_date,
                status="待发货",
                expected_ship_days=self.rng.randint(1, 3),
                expected_delivery_days=self.rng.randint(6, 10),
            )
            if is_positive:
                # 正例：预计发货时间已过，仍未发货。
                order["shipped_at"] = None
                order["status"] = "待发货"
                self.anomalies.append(
                    self._build_anomaly(order, RULE_SHIP_OVERDUE, "高")
                )
            else:
                # 反例：预计发货时间已过，但实际已发货（状态推进为运输中）。
                expected_ship = datetime.strptime(order["expected_ship_at"], "%Y-%m-%dT%H:%M:%S")
                order["shipped_at"] = _iso(expected_ship + timedelta(hours=2))
                order["status"] = "运输中"
                self._add_logistics(
                    order,
                    current_status="运输中",
                    last_updated_at=NOW - timedelta(hours=self.rng.randint(1, 10)),
                    estimated_delivery_at=datetime.strptime(order["expected_delivery_at"], "%Y-%m-%dT%H:%M:%S"),
                )

            self.orders.append(order)
            self._add_order_items(order)
            if is_positive:
                # 正例订单还没有物流记录（尚未发货）。
                pass

    def generate_delivery_stalled_cases(self, count: int) -> None:
        """DELIVERY_STALLED 正例：物流最后更新时间超过阈值，且未签收。
        反例：更新时间接近阈值边界但仍在阈值内（不应触发）。
        """
        threshold = timedelta(hours=DELIVERY_STALLED_HOURS)
        for i in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(8, 20))
            order = self._build_base_order(
                order_date,
                status="运输中",
                expected_ship_days=1,
                expected_delivery_days=self.rng.randint(6, 10),
            )
            expected_ship = datetime.strptime(order["expected_ship_at"], "%Y-%m-%dT%H:%M:%S")
            order["shipped_at"] = _iso(expected_ship + timedelta(hours=1))

            is_positive = i % 2 == 0
            if is_positive:
                last_update = NOW - threshold - timedelta(hours=self.rng.randint(5, 48))
            else:
                # 反例：明显在阈值内（留足安全边际）。
                #
                # 【阶段6修复】此前反例只比阈值少2小时——"扫描新异常"功能用
                # 真实当前时间（而不是种子时NOW）做判断，只要seed脚本运行后
                # 过了2小时以上（完全正常：用户可能当天稍后才点扫描按钮，
                # 或种子生成和扫描操作本身不是原子的），这条"反例"就会被
                # 真实时钟判定为"已超过阈值"，从反例变成了意外的正例。
                # 改为"阈值一半"的安全边际（24小时），只要用户在生成种子
                # 数据后24小时内点击扫描，反例就仍然成立。这是本脚本能
                # 保证的现实边界，不是"永久安全"——如果用户在生成种子数据
                # 超过24小时后才点击扫描，仍可能出现反例"过期"的情况，
                # 这是动态NOW基准固有的权衡，不能被种子脚本单方面消除。
                last_update = NOW - threshold + timedelta(hours=DELIVERY_STALLED_HOURS / 2)

            self.orders.append(order)
            self._add_order_items(order)
            self._add_logistics(
                order,
                current_status="运输中",
                last_updated_at=last_update,
                estimated_delivery_at=datetime.strptime(order["expected_delivery_at"], "%Y-%m-%dT%H:%M:%S"),
                event_count=2,
            )
            if is_positive:
                self.anomalies.append(
                    self._build_anomaly(order, RULE_DELIVERY_STALLED, "中")
                )

    def generate_delivery_overdue_cases(self, count: int) -> None:
        """DELIVERY_OVERDUE 正例：delivered_at > expected_delivery_at。
        反例：delivered_at 略早于 expected_delivery_at（不应触发）。
        """
        for i in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(15, 30))
            order = self._build_base_order(
                order_date,
                status="已签收",
                expected_ship_days=1,
                expected_delivery_days=self.rng.randint(6, 10),
            )
            expected_ship = datetime.strptime(order["expected_ship_at"], "%Y-%m-%dT%H:%M:%S")
            order["shipped_at"] = _iso(expected_ship + timedelta(hours=2))
            expected_delivery = datetime.strptime(order["expected_delivery_at"], "%Y-%m-%dT%H:%M:%S")

            is_positive = i % 2 == 0
            if is_positive:
                delivered_at = expected_delivery + timedelta(hours=self.rng.randint(6, 72))
            else:
                delivered_at = expected_delivery - timedelta(hours=self.rng.randint(1, 10))

            order["delivered_at"] = _iso(delivered_at)
            self.orders.append(order)
            self._add_order_items(order)
            self._add_logistics(
                order,
                current_status="已签收",
                last_updated_at=delivered_at,
                estimated_delivery_at=expected_delivery,
                event_count=4,
            )
            if is_positive:
                self.anomalies.append(
                    self._build_anomaly(order, RULE_DELIVERY_OVERDUE, "中")
                )

    def generate_supplier_prep_delay_cases(self, count: int) -> None:
        """SUPPLIER_PREP_DELAY 正例：备货状态更新时间超过阈值仍未完成备货。
        反例：更新时间在阈值内。

        注意：此规则依赖的 supplier_prep_status / supplier_prep_updated_at
        字段是本阶段对技术方案 §3 原始字段列表的补充（见 schema.sql 中的
        说明注释），用户尚未确认该设计。
        """
        threshold = timedelta(hours=SUPPLIER_PREP_DELAY_HOURS)
        for i in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(3, 10))
            order = self._build_base_order(
                order_date,
                status="待发货",
                expected_ship_days=self.rng.randint(3, 6),
                expected_delivery_days=self.rng.randint(10, 15),
            )

            # 【修复】此前 expected_ship_at 以 order_date 为基准计算，
            # order_date 可能晚于 NOW - expected_ship_days 太多导致
            # expected_ship_at 落在 NOW 之前——这会让这批"只为测试
            # SUPPLIER_PREP_DELAY"的订单意外同时满足 SHIP_OVERDUE 的
            # 判断条件（未发货 + 预计发货时间已过），污染该规则的测试样本。
            # 显式将 expected_ship_at 固定在 NOW 之后，确保该批订单只
            # 触发本规则，不触发 SHIP_OVERDUE。
            order["expected_ship_at"] = _iso(NOW + timedelta(days=self.rng.randint(2, 5)))

            is_positive = i % 2 == 0
            if is_positive:
                order["supplier_prep_status"] = "待备货"
                order["supplier_prep_updated_at"] = _iso(NOW - threshold - timedelta(hours=self.rng.randint(5, 40)))
            else:
                order["supplier_prep_status"] = "备货中"
                # 【阶段6修复】同 DELIVERY_STALLED 反例的问题：原边际只有3小时，
                # 不足以抵抗"种子生成"和"用户点击扫描"之间的真实时间差。
                # 改为阈值一半（36小时）的安全边际。
                order["supplier_prep_updated_at"] = _iso(
                    NOW - threshold + timedelta(hours=SUPPLIER_PREP_DELAY_HOURS / 2)
                )

            self.orders.append(order)
            self._add_order_items(order)
            if is_positive:
                self.anomalies.append(
                    self._build_anomaly(order, RULE_SUPPLIER_PREP_DELAY, "中")
                )

    def generate_status_conflict_cases(self, count: int) -> None:
        """STATUS_CONFLICT 正例：订单状态与物流状态命中预定义不合理组合。
        反例：组合是合理的常见搭配。
        """
        for i in range(count):
            order_date = NOW - timedelta(days=self.rng.randint(5, 20))
            is_positive = i % 2 == 0

            if is_positive:
                order_status, logi_status = self.rng.choice(STATUS_CONFLICT_PAIRS)
            else:
                order_status, logi_status = ("运输中", "运输中")

            order = self._build_base_order(
                order_date,
                status=order_status,
                expected_ship_days=1,
                expected_delivery_days=self.rng.randint(6, 10),
            )
            if order_status in ("运输中", "已签收"):
                expected_ship = datetime.strptime(order["expected_ship_at"], "%Y-%m-%dT%H:%M:%S")
                order["shipped_at"] = _iso(expected_ship + timedelta(hours=2))
            if order_status == "已签收":
                order["delivered_at"] = order["shipped_at"]

            # 【修复】与 SUPPLIER_PREP_DELAY 修复同类问题：当 order_status
            # 为"待确认"时 shipped_at 仍为 None，而 expected_ship_at（基于
            # order_date 计算）可能落在 NOW 之前，导致这批专为测试
            # STATUS_CONFLICT 构造的订单意外也满足 SHIP_OVERDUE 的条件
            # （状态只要不是"已取消"就不受排除）。已取消的订单不受此问题
            # 影响（SHIP_OVERDUE 明确排除已取消订单），故只需处理"待确认"
            # 且未发货的情况。
            if order["shipped_at"] is None and order_status != "已取消":
                order["expected_ship_at"] = _iso(NOW + timedelta(days=self.rng.randint(2, 5)))

            self.orders.append(order)
            self._add_order_items(order)
            self._add_logistics(
                order,
                current_status=logi_status,
                last_updated_at=NOW - timedelta(hours=self.rng.randint(1, 10)),
                estimated_delivery_at=datetime.strptime(order["expected_delivery_at"], "%Y-%m-%dT%H:%M:%S"),
            )
            if is_positive:
                self.anomalies.append(
                    self._build_anomaly(order, RULE_STATUS_CONFLICT, "高")
                )

    def _build_anomaly(self, order: dict, rule_code: str, severity: str) -> dict:
        type_labels = {
            RULE_SHIP_OVERDUE: "超时未发货",
            RULE_DELIVERY_STALLED: "物流延迟",
            RULE_DELIVERY_OVERDUE: "履约超时",
            RULE_SUPPLIER_PREP_DELAY: "供应商备货异常",
            RULE_STATUS_CONFLICT: "订单状态异常",
        }
        return {
            "anomaly_id": _new_id("ANOM", self.rng),
            "order_id": order["order_id"],
            "anomaly_type": type_labels[rule_code],
            "detected_at": _iso(NOW - timedelta(hours=self.rng.randint(1, 48))),
            "rule_code": rule_code,
            "severity": severity,
            "status": "待确认",
            "resolved_at": None,
        }

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.generate_customers(CUSTOMER_COUNT)
        self.generate_suppliers(SUPPLIER_COUNT)
        self.generate_normal_orders(NORMAL_ORDER_COUNT)
        self.generate_ship_overdue_cases(ANOMALY_CASE_MULTIPLIER * 2)
        self.generate_delivery_stalled_cases(ANOMALY_CASE_MULTIPLIER * 2)
        self.generate_delivery_overdue_cases(ANOMALY_CASE_MULTIPLIER * 2)
        self.generate_supplier_prep_delay_cases(ANOMALY_CASE_MULTIPLIER * 2)
        self.generate_status_conflict_cases(ANOMALY_CASE_MULTIPLIER * 2)


# ----------------------------------------------------------------------
# 数据库写入
# ----------------------------------------------------------------------


def _table_has_rows(conn: sqlite3.Connection, table: str) -> bool:
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
    return cursor.fetchone()[0] > 0


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)


def insert_all(conn: sqlite3.Connection, gen: SeedGenerator) -> None:
    conn.executemany(
        """INSERT INTO customers (customer_id, name, industry, tier, status, created_at)
           VALUES (:customer_id, :name, :industry, :tier, :status, :created_at)""",
        gen.customers,
    )
    conn.executemany(
        """INSERT INTO suppliers (supplier_id, name, category, status, lead_time_days)
           VALUES (:supplier_id, :name, :category, :status, :lead_time_days)""",
        gen.suppliers,
    )
    conn.executemany(
        """INSERT INTO orders (
               order_id, customer_id, supplier_id, order_date, amount, status,
               expected_ship_at, shipped_at, expected_delivery_at, delivered_at,
               supplier_prep_status, supplier_prep_updated_at
           ) VALUES (
               :order_id, :customer_id, :supplier_id, :order_date, :amount, :status,
               :expected_ship_at, :shipped_at, :expected_delivery_at, :delivered_at,
               :supplier_prep_status, :supplier_prep_updated_at
           )""",
        gen.orders,
    )
    conn.executemany(
        """INSERT INTO order_items (item_id, order_id, product_name, quantity, unit_price)
           VALUES (:item_id, :order_id, :product_name, :quantity, :unit_price)""",
        gen.order_items,
    )
    conn.executemany(
        """INSERT INTO logistics (logistics_id, order_id, current_status, last_updated_at, estimated_delivery_at)
           VALUES (:logistics_id, :order_id, :current_status, :last_updated_at, :estimated_delivery_at)""",
        gen.logistics,
    )
    conn.executemany(
        """INSERT INTO logistics_events (event_id, logistics_id, event_time, location, event_status, description)
           VALUES (:event_id, :logistics_id, :event_time, :location, :event_status, :description)""",
        gen.logistics_events,
    )
    conn.executemany(
        """INSERT INTO anomalies (anomaly_id, order_id, anomaly_type, detected_at, rule_code, severity, status, resolved_at)
           VALUES (:anomaly_id, :order_id, :anomaly_type, :detected_at, :rule_code, :severity, :status, :resolved_at)""",
        gen.anomalies,
    )


def reset_database(db_path: Path, schema_path: Path) -> None:
    """删除并重建数据库文件，用于 --force 场景。"""
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    apply_schema(conn, schema_path)
    conn.commit()
    conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="FlowLens AI 模拟数据生成脚本")
    parser.add_argument(
        "--force",
        action="store_true",
        help="若数据库已存在数据，先清空重建再生成（默认：若已有数据则跳过，不重复插入）",
    )
    args = parser.parse_args()

    config = get_config()
    db_path = config.database_path
    schema_path = Path(__file__).resolve().parent / "schema.sql"

    if args.force and db_path.exists():
        print(f"[seed] --force 指定，删除并重建数据库: {db_path}")
        reset_database(db_path, schema_path)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON;")
        apply_schema(conn, schema_path)
        conn.commit()
        if _table_has_rows(conn, "customers"):
            print(
                f"[seed] 数据库 {db_path} 中 customers 表已有数据，跳过生成"
                "（避免重复初始化产生重复数据）。如需重新生成，请加 --force。"
            )
            conn.close()
            return 0
        conn.close()

    print("[seed] 开始生成模拟数据 ...")
    gen = SeedGenerator(seed=SEED)
    gen.run()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        insert_all(conn, gen)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"[seed] 插入失败，已回滚: {exc}", file=sys.stderr)
        conn.close()
        return 1
    conn.close()

    print("[seed] 生成完成：")
    print(f"  customers:        {len(gen.customers)}")
    print(f"  suppliers:        {len(gen.suppliers)}")
    print(f"  orders:           {len(gen.orders)}")
    print(f"  order_items:      {len(gen.order_items)}")
    print(f"  logistics:        {len(gen.logistics)}")
    print(f"  logistics_events: {len(gen.logistics_events)}")
    print(f"  anomalies:        {len(gen.anomalies)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
