"""
AI 诊断服务单元测试。

对应技术方案§9："测试AI输出解析失败、服务不可用和空输入情况。"
以及产品需求§15.3验收原则："AI诊断能区分事实、推测和待核实信息。"
"""

from __future__ import annotations

import unittest

from models.schemas import RuleViolation
from services import ai_service


def _make_violation(rule_code: str, **evidence) -> RuleViolation:
    return RuleViolation(
        order_id="ORD-TEST001",
        rule_code=rule_code,
        anomaly_type="测试类型",
        severity="高",
        evidence=evidence or {"field": "value"},
    )


class TestDiagnoseAnomaly(unittest.TestCase):
    def test_all_five_rule_types_produce_valid_diagnosis(self):
        """五种规则类型都应能生成通过schema校验的诊断结果
        （产品需求§15.1：至少覆盖三类规则，本项目实现了全部五类）。
        """
        rule_codes = ["SHIP_OVERDUE", "DELIVERY_STALLED", "DELIVERY_OVERDUE",
                      "SUPPLIER_PREP_DELAY", "STATUS_CONFLICT"]
        for code in rule_codes:
            violation = _make_violation(code)
            result = ai_service.diagnose_anomaly(violation)
            self.assertEqual(result.model_type, "mock")
            self.assertTrue(result.summary)
            self.assertGreater(len(result.possible_causes), 0)

    def test_summary_references_order_id(self):
        """诊断摘要应引用具体订单编号，保证可追溯性
        （产品需求§5.4.2："AI结果必须能追溯到输入的...字段"）。
        """
        violation = _make_violation("SHIP_OVERDUE")
        result = ai_service.diagnose_anomaly(violation)
        self.assertIn("ORD-TEST001", result.summary)

    def test_evidence_in_causes_references_input_evidence(self):
        """可能原因里引用的证据必须来自传入的 violation.evidence，
        不能凭空编造字段名。
        """
        violation = _make_violation(
            "SHIP_OVERDUE", expected_ship_at="2024-03-10T10:00:00", shipped_at="未发货"
        )
        result = ai_service.diagnose_anomaly(violation)
        all_evidence_text = " ".join(
            e for c in result.possible_causes for e in c.evidence
        )
        self.assertIn("2024-03-10T10:00:00", all_evidence_text)

    def test_confidence_levels_are_valid(self):
        """每条可能原因必须标注confidence，且取值合法——这是区分
        "事实"和"推测"的关键机制（产品需求§15.3验收点）。
        """
        violation = _make_violation("DELIVERY_OVERDUE")
        result = ai_service.diagnose_anomaly(violation)
        for cause in result.possible_causes:
            self.assertIn(cause.confidence, ai_service.VALID_CONFIDENCE)

    def test_unsupported_rule_code_raises_clear_error(self):
        """不在模板清单里的规则代码应明确报错，不应该返回编造的诊断
        （不允许"伪装成功"）。
        """
        violation = _make_violation("UNKNOWN_RULE_XYZ")
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.diagnose_anomaly(violation)

    def test_real_model_type_not_available_raises_clear_error(self):
        """阶段8之前，model_type="real" 必须明确报错，不能静默降级为mock
        （静默降级本身是一种伪装成功）。
        """
        violation = _make_violation("SHIP_OVERDUE")
        with self.assertRaises(ai_service.DiagnosisError) as ctx:
            ai_service.diagnose_anomaly(violation, model_type="real")
        self.assertIn("real", str(ctx.exception).lower())


class TestSchemaValidation(unittest.TestCase):
    def test_valid_payload_passes(self):
        payload = {
            "summary": "测试摘要",
            "possible_causes": [{"cause": "测试原因", "evidence": ["字段=值"], "confidence": "medium"}],
            "customer_impact": "测试影响",
            "risk_level": "medium",
            "priority": "P2",
            "recommendations": ["测试建议"],
            "communication_draft": "测试文案",
            "verification_required": ["测试待核实项"],
            "model_type": "mock",
        }
        result = ai_service.validate_diagnosis_payload(payload)
        self.assertEqual(result.summary, "测试摘要")

    def test_missing_required_field_rejected(self):
        payload = {"summary": "测试"}
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_empty_summary_rejected(self):
        payload = {
            "summary": "   ",
            "possible_causes": [{"cause": "x", "confidence": "low"}],
            "customer_impact": "x", "risk_level": "low", "priority": "P3",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "mock",
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_empty_possible_causes_rejected(self):
        """possible_causes 不能为空——AI诊断必须给出至少一个可能原因，
        否则"诊断"本身没有意义。
        """
        payload = {
            "summary": "测试",
            "possible_causes": [],
            "customer_impact": "x", "risk_level": "low", "priority": "P3",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "mock",
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_invalid_confidence_rejected(self):
        payload = {
            "summary": "测试",
            "possible_causes": [{"cause": "x", "confidence": "超级确定"}],
            "customer_impact": "x", "risk_level": "low", "priority": "P3",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "mock",
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_invalid_risk_level_rejected(self):
        payload = {
            "summary": "测试",
            "possible_causes": [{"cause": "x", "confidence": "low"}],
            "customer_impact": "x", "risk_level": "超高", "priority": "P3",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "mock",
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_invalid_priority_rejected(self):
        payload = {
            "summary": "测试",
            "possible_causes": [{"cause": "x", "confidence": "low"}],
            "customer_impact": "x", "risk_level": "low", "priority": "P0",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "mock",
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_invalid_model_type_rejected(self):
        payload = {
            "summary": "测试",
            "possible_causes": [{"cause": "x", "confidence": "low"}],
            "customer_impact": "x", "risk_level": "low", "priority": "P3",
            "recommendations": [], "communication_draft": "", "verification_required": [],
            "model_type": "gpt4",  # 不是 mock/real
        }
        with self.assertRaises(ai_service.DiagnosisError):
            ai_service.validate_diagnosis_payload(payload)

    def test_to_json_fields_produces_storable_dict(self):
        """to_json_fields() 的输出应能直接用于写入 ai_diagnoses 表。"""
        violation = _make_violation("SHIP_OVERDUE")
        result = ai_service.diagnose_anomaly(violation)
        fields = result.to_json_fields()
        self.assertIn("causes_json", fields)
        self.assertIn("recommendations_json", fields)
        self.assertIn("verification_json", fields)

        import json
        causes = json.loads(fields["causes_json"])
        self.assertIsInstance(causes, list)
        self.assertTrue(all("confidence" in c for c in causes))


if __name__ == "__main__":
    unittest.main()
