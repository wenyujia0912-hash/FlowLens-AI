"""
AI 诊断服务 —— 统一接口 + Mock Provider。

职责边界（阶段0确认、技术方案§6要求）：
    - 本模块提供 diagnose_anomaly(context) -> DiagnosisResult 的统一接口。
      当前只实现 MockAIProvider；RealAIProvider 要等 Mock 稳定、用户确认
      接入真实LLM API后才在阶段8添加，两者共用同一接口和同一校验逻辑。
    - 规则判断已经在 rule_engine.py 完成，本模块**不重复做任何确定性判断**，
      只基于规则引擎已经给出的事实（RuleViolation.evidence）做"解释、归纳
      和建议"（产品需求§5.4）。
    - Mock 的"归纳"是基于规则类型的模板化文案（不是调用任何外部服务），
      但输出结构和真实LLM的输出结构完全一致，确保业务层代码不用关心
      当前到底是mock还是真实模型。
    - AI 不直接修改任何业务数据——本模块的函数只返回 DiagnosisResult，
      不接触数据库写操作。是否要存入 ai_diagnoses 表、是否要创建任务，
      都由调用方（页面层，在用户明确确认后）决定。

输出 JSON 结构（技术方案§6原文）：
    {
      "summary": "...",
      "possible_causes": [{"cause": "...", "evidence": [...], "confidence": "low|medium|high"}],
      "customer_impact": "...",
      "risk_level": "low|medium|high",
      "priority": "P1|P2|P3",
      "recommendations": ["..."],
      "communication_draft": "...",
      "verification_required": ["..."]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from models.schemas import RuleViolation

VALID_CONFIDENCE = ("low", "medium", "high")
VALID_RISK_LEVELS = ("low", "medium", "high")
VALID_PRIORITIES = ("P1", "P2", "P3")

# 风险等级在中英文之间的映射：数据库 anomalies.severity 用中文（高/中/低），
# AI诊断结果的 risk_level 按技术方案§6原文用英文（low/medium/high）。
# 两者是不同的字段（一个是规则初始评估，一个是AI建议），本模块统一维护映射关系。
SEVERITY_ZH_TO_EN = {"高": "high", "中": "medium", "低": "low"}
SEVERITY_EN_TO_ZH = {v: k for k, v in SEVERITY_ZH_TO_EN.items()}


@dataclass
class PossibleCause:
    cause: str
    evidence: list[str]
    confidence: str  # low | medium | high


@dataclass
class DiagnosisResult:
    summary: str
    possible_causes: list[PossibleCause]
    customer_impact: str
    risk_level: str  # low | medium | high
    priority: str  # P1 | P2 | P3
    recommendations: list[str]
    communication_draft: str
    verification_required: list[str]
    model_type: str  # mock | real
    generated_at: str

    def to_json_fields(self) -> dict:
        """转换为可直接存入 ai_diagnoses 表的字段字典。"""
        return {
            "summary": self.summary,
            "causes_json": json.dumps(
                [{"cause": c.cause, "evidence": c.evidence, "confidence": c.confidence} for c in self.possible_causes],
                ensure_ascii=False,
            ),
            "impact": self.customer_impact,
            "risk_suggestion": self.risk_level,
            "recommendations_json": json.dumps(self.recommendations, ensure_ascii=False),
            "communication_draft": self.communication_draft,
            "verification_json": json.dumps(self.verification_required, ensure_ascii=False),
            "model_type": self.model_type,
            "generated_at": self.generated_at,
        }


class DiagnosisError(Exception):
    """AI 诊断失败（服务不可用、输出校验失败等）时抛出。

    调用方（页面层）应捕获此异常并展示明确提示，同时保留"规则结果和
    人工创建任务的能力"（产品需求§5.4.2、页面交互设计§5的硬性要求）。
    """


# ----------------------------------------------------------------------
# Schema 校验（Mock 和未来的 Real Provider 共用）
# ----------------------------------------------------------------------


def validate_diagnosis_payload(payload: dict) -> DiagnosisResult:
    """校验一个诊断结果字典是否符合统一 schema，返回结构化对象。

    任何 Provider（Mock 或未来的 Real）的输出都必须先经过这个函数，
    校验失败应抛出 DiagnosisError，不允许将未经校验的数据直接写入数据库
    （技术方案§6："AI 输出必须进行 JSON/schema 校验；无效输出应提示
    错误并允许重试"）。
    """
    required_fields = (
        "summary", "possible_causes", "customer_impact", "risk_level",
        "priority", "recommendations", "communication_draft",
        "verification_required", "model_type",
    )
    missing = [f for f in required_fields if f not in payload]
    if missing:
        raise DiagnosisError(f"诊断结果缺少必填字段: {missing}")

    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise DiagnosisError("summary 必须是非空字符串")

    if not isinstance(payload["possible_causes"], list) or not payload["possible_causes"]:
        raise DiagnosisError("possible_causes 必须是非空列表")

    causes = []
    for i, c in enumerate(payload["possible_causes"]):
        if not isinstance(c, dict) or "cause" not in c or "confidence" not in c:
            raise DiagnosisError(f"possible_causes[{i}] 缺少必要字段 cause/confidence")
        if c["confidence"] not in VALID_CONFIDENCE:
            raise DiagnosisError(f"possible_causes[{i}].confidence 不合法: {c['confidence']}")
        evidence = c.get("evidence", [])
        if not isinstance(evidence, list):
            raise DiagnosisError(f"possible_causes[{i}].evidence 必须是列表")
        causes.append(PossibleCause(cause=c["cause"], evidence=evidence, confidence=c["confidence"]))

    if payload["risk_level"] not in VALID_RISK_LEVELS:
        raise DiagnosisError(f"risk_level 不合法: {payload['risk_level']}")
    if payload["priority"] not in VALID_PRIORITIES:
        raise DiagnosisError(f"priority 不合法: {payload['priority']}")
    if not isinstance(payload["recommendations"], list):
        raise DiagnosisError("recommendations 必须是列表")
    if not isinstance(payload["verification_required"], list):
        raise DiagnosisError("verification_required 必须是列表")
    if payload["model_type"] not in ("mock", "real"):
        raise DiagnosisError(f"model_type 不合法: {payload['model_type']}")

    return DiagnosisResult(
        summary=payload["summary"],
        possible_causes=causes,
        customer_impact=payload["customer_impact"],
        risk_level=payload["risk_level"],
        priority=payload["priority"],
        recommendations=list(payload["recommendations"]),
        communication_draft=payload.get("communication_draft", ""),
        verification_required=list(payload["verification_required"]),
        model_type=payload["model_type"],
        generated_at=payload.get("generated_at") or datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    )


# ----------------------------------------------------------------------
# Mock Provider：按规则类型生成模板化、但结构真实的诊断
# ----------------------------------------------------------------------

_TEMPLATES = {
    "SHIP_OVERDUE": {
        "summary_fmt": "订单 {order_id} 已超过预计发货时间仍未发货，触发超时未发货规则。",
        "causes": [
            {
                "cause": "供应商备货或仓库出库流程延迟，导致未能按时完成发货操作",
                "evidence_keys": ["expected_ship_at", "shipped_at"],
                "confidence": "medium",
            },
            {
                "cause": "订单可能存在信息错误（如地址、商品规格待确认）导致发货被搁置",
                "evidence_keys": [],
                "confidence": "low",
            },
        ],
        "impact": "客户可能因发货延迟而产生不满，若涉及时效敏感商品，可能影响客户后续复购意愿。",
        "risk_level": "high",
        "priority": "P1",
        "recommendations": [
            "立即联系供应商确认备货和发货进度",
            "如无法在24小时内发货，主动联系客户说明情况并给出新的预计时间",
        ],
        "communication_draft": "您好，关于订单 {order_id}，我们注意到发货时间略有延迟，正在加急处理，预计会在最短时间内安排发货，给您带来的不便我们深表歉意。",
        "verification_required": ["供应商当前实际备货进度（系统数据未直接反映）", "是否已与客户进行过初步沟通"],
    },
    "DELIVERY_STALLED": {
        "summary_fmt": "订单 {order_id} 的物流信息长时间未更新，可能处于停滞或异常状态。",
        "causes": [
            {
                "cause": "物流途中可能发生中转延误、分拨中心积压或异常事件",
                "evidence_keys": ["logistics_last_updated_at", "logistics_status"],
                "confidence": "medium",
            },
            {
                "cause": "物流信息同步系统可能存在数据更新延迟，实际运输状态未必真的停滞",
                "evidence_keys": [],
                "confidence": "low",
            },
        ],
        "impact": "客户可能因包裹长时间无更新而产生焦虑或投诉，如遇季节性时效商品，影响更明显。",
        "risk_level": "medium",
        "priority": "P2",
        "recommendations": [
            "联系物流承运商核实包裹实际位置和状态",
            "若确认延误，主动告知客户并说明预计恢复时间",
        ],
        "communication_draft": "您好，关于订单 {order_id} 的物流，我们注意到近期更新较慢，已在联系物流公司核实具体情况，会尽快给您反馈最新进展。",
        "verification_required": ["物流承运商处的实际运输状态", "是否为系统同步延迟而非真实停滞"],
    },
    "DELIVERY_OVERDUE": {
        "summary_fmt": "订单 {order_id} 实际签收时间晚于预计送达时间，已构成履约超时。",
        "causes": [
            {
                "cause": "物流配送环节效率不足或路途遇到不可控延误",
                "evidence_keys": ["delivered_at", "expected_delivery_at"],
                "confidence": "medium",
            },
            {
                "cause": "预计送达时间的估算本身可能偏保守或不准确",
                "evidence_keys": [],
                "confidence": "low",
            },
        ],
        "impact": "履约超时直接影响客户体验，若该客户为重点/战略客户，可能影响长期合作信任度。",
        "risk_level": "medium",
        "priority": "P2",
        "recommendations": [
            "分析该物流路线/承运商是否存在系统性延误问题",
            "考虑对本次超时给予客户适当补偿或说明",
        ],
        "communication_draft": "您好，订单 {order_id} 的签收时间略晚于预计，为此带来的不便我们表示歉意，我们会持续关注物流时效并加以改进。",
        "verification_required": ["本次延误是否为孤立事件还是该物流路线的系统性问题"],
    },
    "SUPPLIER_PREP_DELAY": {
        "summary_fmt": "订单 {order_id} 对应供应商备货状态更新滞后，超过正常时限。",
        "causes": [
            {
                "cause": "供应商当前产能或库存不足，备货进度落后于预期",
                "evidence_keys": ["supplier_prep_status", "supplier_prep_updated_at"],
                "confidence": "medium",
            },
            {
                "cause": "供应商可能未及时在系统中同步最新备货状态，实际进度未必滞后",
                "evidence_keys": [],
                "confidence": "low",
            },
        ],
        "impact": "若备货持续滞后，将直接推迟发货时间，进而影响客户收货体验，形成连锁风险。",
        "risk_level": "medium",
        "priority": "P2",
        "recommendations": [
            "与供应商确认当前真实备货进度，并要求同步更新系统状态",
            "评估是否需要寻找备用供应商以降低风险",
        ],
        "communication_draft": "（本条建议为内部沟通参考，不直接发送给客户）需与供应商核实备货进度，视情况决定是否需要调整发货计划或提前告知客户。",
        "verification_required": ["供应商的真实备货进度", "是否存在替代供应渠道"],
    },
    "STATUS_CONFLICT": {
        "summary_fmt": "订单 {order_id} 的订单状态与物流状态出现不合理组合，数据存在矛盾。",
        "causes": [
            {
                "cause": "订单取消后，物流侧未同步终止导致状态不一致",
                "evidence_keys": ["order_status", "logistics_status"],
                "confidence": "medium",
            },
            {
                "cause": "系统集成或数据同步环节存在延迟或错误",
                "evidence_keys": [],
                "confidence": "low",
            },
        ],
        "impact": "状态矛盾可能导致客户收到错误通知（例如订单已取消却收到发货提醒），影响客户信任。",
        "risk_level": "high",
        "priority": "P1",
        "recommendations": [
            "人工核实订单真实状态，确认是否需要拦截物流或更正订单状态",
            "排查系统集成环节，避免类似状态不一致再次出现",
        ],
        "communication_draft": "（本条建议为内部沟通参考）请先核实订单真实状态，如确认订单已取消但物流仍在运行，需立即联系物流方拦截。",
        "verification_required": ["订单的真实最新状态（以人工核实为准）", "是否已产生实际物流动作"],
    },
}


def _build_mock_result(violation: RuleViolation) -> DiagnosisResult:
    template = _TEMPLATES.get(violation.rule_code)
    if template is None:
        raise DiagnosisError(f"没有为规则代码 {violation.rule_code} 配置 Mock 诊断模板")

    causes = []
    for c in template["causes"]:
        evidence_strs = [
            f"{k}={violation.evidence[k]}" for k in c["evidence_keys"] if k in violation.evidence
        ]
        causes.append(
            PossibleCause(cause=c["cause"], evidence=evidence_strs, confidence=c["confidence"])
        )

    return DiagnosisResult(
        summary=template["summary_fmt"].format(order_id=violation.order_id),
        possible_causes=causes,
        customer_impact=template["impact"],
        risk_level=template["risk_level"],
        priority=template["priority"],
        recommendations=list(template["recommendations"]),
        communication_draft=template["communication_draft"].format(order_id=violation.order_id),
        verification_required=list(template["verification_required"]),
        model_type="mock",
        generated_at=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    )


def diagnose_anomaly(violation: RuleViolation, *, model_type: str = "mock") -> DiagnosisResult:
    """统一诊断入口。当前只支持 model_type="mock"。

    参数:
        violation: 规则引擎给出的判断结果（含 rule_code 和 evidence），
            本函数**不会**重新去查数据库或重新做规则判断，只基于已有的
            事实做归纳。
        model_type: 预留参数，阶段8接入真实模型后，这里会根据
            config.settings 的 AI_MODE 决定调用 MockProvider 还是
            RealProvider。当前只有 mock 可用，传其他值会报错而不是
            静默降级——"静默降级"本身就是一种伪装成功的行为，不允许。

    返回:
        DiagnosisResult，已经过 schema 校验。

    异常:
        DiagnosisError: 没有对应规则的模板、或输出校验失败。
    """
    if model_type != "mock":
        raise DiagnosisError(
            f"model_type={model_type!r} 当前不可用：真实AI Provider 尚未实现"
            "（需等待阶段8，且需 AI_MODE=real 且配置 AI_API_KEY）。"
        )

    result = _build_mock_result(violation)

    # 即使是本模块自己生成的结果，也要走一遍统一校验，确保未来替换成
    # 真实模型输出时，校验逻辑已经是被验证过的（校验路径不因调用方是
    # mock还是real而分叉）。
    payload = {
        "summary": result.summary,
        "possible_causes": [
            {"cause": c.cause, "evidence": c.evidence, "confidence": c.confidence}
            for c in result.possible_causes
        ],
        "customer_impact": result.customer_impact,
        "risk_level": result.risk_level,
        "priority": result.priority,
        "recommendations": result.recommendations,
        "communication_draft": result.communication_draft,
        "verification_required": result.verification_required,
        "model_type": result.model_type,
        "generated_at": result.generated_at,
    }
    return validate_diagnosis_payload(payload)


def supported_rule_codes() -> tuple[str, ...]:
    """返回当前 Mock Provider 支持诊断的规则代码列表，供页面层判断
    "这条异常能否发起诊断"。
    """
    return tuple(_TEMPLATES.keys())
