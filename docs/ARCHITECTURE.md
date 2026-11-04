# FlowLens AI 技术架构说明

## 1. 分层架构

```
┌─────────────────────────────────────────────┐
│  pages/ (Streamlit 页面)                      │  只负责UI渲染、调用service、展示结果
├─────────────────────────────────────────────┤
│  services/ (业务逻辑)                          │  规则判断、状态流转、数据聚合、校验
├─────────────────────────────────────────────┤
│  repositories/ (数据访问)                      │  只做SQL读写，不含业务判断
├─────────────────────────────────────────────┤
│  database/ (SQLite)                           │  单一事实来源
└─────────────────────────────────────────────┘
        ↑
  config/ (配置) 和 models/ (跨层数据结构) 横向被各层引用
```

**分层原则**：页面代码不直接写SQL；规则判断逻辑只存在于 `services/rule_engine.py`；数据访问函数不做业务决策（例如"异常是否该关闭"不是repository该管的事）。

## 2. 模块与数据流

```
                    ┌──────────────┐
                    │   customers   │
                    └──────┬───────┘
                           │ 1:N
                    ┌──────▼───────┐      ┌──────────────┐
                    │    orders     │◀─────│   suppliers   │
                    └──────┬───────┘ N:1   └──────────────┘
          ┌────────────────┼────────────────┐
          │ 1:N             │ 1:1             │ 1:N
   ┌──────▼──────┐  ┌───────▼──────┐  ┌──────▼───────┐
   │ order_items  │  │  logistics    │  │  anomalies    │
   └─────────────┘  └───────┬──────┘  └──────┬───────┘
                             │ 1:N             │ 1:N
                     ┌───────▼──────┐  ┌──────▼───────┐
                     │logistics_events│  │ ai_diagnoses │
                     └──────────────┘  └──────────────┘
                                               │ 0/1:N (nullable FK)
                                        ┌──────▼───────┐
                                        │operation_tasks│
                                        └──────┬───────┘
                                               │ 1:N
                                        ┌──────▼───────┐
                                        │  task_logs    │
                                        └──────────────┘
```

**关键约束**（均在 `database/schema.sql` 用CHECK约束强制，不只是文档层面的约定）：
- 订单金额/数量/单价不得为负
- 实际发货时间 ≥ 下单时间；实际签收时间 ≥ 发货时间
- 已完成任务必须有 `result` 和 `completed_at`
- `operation_tasks.anomaly_id` / `order_id` 均为nullable，支持手动创建一般任务

## 3. 规则引擎设计

`services/rule_engine.py` 是全系统**唯一**做异常触发判断的地方。五条规则（见`docs/PRODUCT.md`）都实现为独立的纯函数，不访问数据库，只接受已经查出来的订单数据（含物流JOIN结果），返回判断结果：

```python
def check_ship_overdue(order_row, now: datetime) -> RuleViolation | None:
    ...
```

每条规则命中时返回的 `RuleViolation` 带有 `evidence` 字典（触发依据的具体字段值），这是后续AI诊断"可追溯到真实事实"的基础。

**去重机制**（`services/anomaly_service.py`）：同一订单同一规则代码，在"待确认/处理中"状态下只保留一条活跃异常。扫描时先查`find_active_by_order_and_rule`，命中就跳过，不会重复创建。

**阈值集中配置**（`config/anomaly_rules.py`）：物流停滞阈值（48小时）、供应商备货延迟阈值（72小时）、状态冲突组合清单都在这一个文件里，修改阈值不需要碰业务逻辑代码。

## 4. AI 诊断设计

### 4.1 统一接口

```python
def diagnose_anomaly(violation: RuleViolation, *, model_type: str = "mock") -> DiagnosisResult:
```

所有诊断调用都走这一个函数。`model_type="real"` 当前会**显式报错**（不是静默降级成mock），这是故意的设计——避免"用户以为接了真实AI、实际在用Mock"的误导。

### 4.2 输出 Schema

```json
{
  "summary": "对异常事实的简明概述",
  "possible_causes": [
    {"cause": "可能原因", "evidence": ["字段=值"], "confidence": "low|medium|high"}
  ],
  "customer_impact": "客户影响分析",
  "risk_level": "low|medium|high",
  "priority": "P1|P2|P3",
  "recommendations": ["可执行建议"],
  "communication_draft": "沟通参考文本",
  "verification_required": ["需要进一步核实的信息"],
  "model_type": "mock|real"
}
```

Mock和未来的Real Provider**共用同一个校验函数**`validate_diagnosis_payload()`——Mock自己生成的结果也要过这一关，保证校验逻辑本身是被验证过的，不是只在"假设未来接入真实模型"时才生效。

### 4.3 Mock 的具体实现

针对5种规则代码各维护一套模板（`services/ai_service.py` 的 `_TEMPLATES`），模板包含固定的中文文案结构，用具体订单的字段值（如订单编号）填充占位符。`possible_causes[].evidence`直接引用传入的`RuleViolation.evidence`里的字段值，不会编造输入里没有的内容。

### 4.4 真实AI扩展方式

接入真实LLM API的改动范围：

1. 在`services/ai_service.py`新增`_call_real_model(violation) -> dict`，发起真实API请求，返回原始响应
2. `diagnose_anomaly()`里`model_type == "real"`分支改为调用这个函数，而不是抛错
3. 真实模型的原始输出同样要经过`validate_diagnosis_payload()`校验——这一步代码已经写好，不需要改
4. API Key从`config.settings.get_config().ai_api_key`读取（环境变量`AI_API_KEY`），已经预留好读取逻辑
5. 需要新增：超时控制、失败重试（最多1次）、Prompt模板管理

**不需要改的部分**：`anomaly_service.run_diagnosis()`、页面层的四区展示逻辑、数据库schema——这些都只依赖`DiagnosisResult`这个统一结构，不关心数据从哪来。这是分层设计的直接收益：换AI实现不需要动业务流程代码。

## 5. 任务与异常状态独立性

这是本项目反复强调的一个架构约束：`anomalies.status` 和 `operation_tasks.status` 是两个完全独立的状态机，没有数据库外键级别的联动触发器，联动只能通过service层的**显式调用**发生（例如创建任务时`anomaly_service.mark_in_progress()`是在页面代码里紧跟着`task_service.create_task()`之后手动调用的，不是数据库trigger自动做的）。这样设计是为了保证"任务完成≠异常解决"这条业务规则不会被意外破坏。

## 6. 为什么选择标准库实现Excel导出

技术方案原本建议pandas+openpyxl，但开发环境网络受限无法安装。`.xlsx`文件本质是遵循OOXML规范的ZIP包，`services/export_service.py`用标准库`zipfile`直接生成——对"纯表格数据，不要公式不要样式"这个场景，不需要pandas的完整能力。已用`unzip`、`xml.etree.ElementTree`解析校验、macOS系统`file`命令独立验证过生成文件的格式有效性。网络恢复后，可以用`pandas.DataFrame(rows).to_excel(path)`替换这部分实现，代码量会更少。

## 7. 测试策略

由于开发环境无法安装`streamlit`，所有页面级验证都通过**最小化模拟streamlit API**（只实现页面实际调用到的`st.*`函数，返回确定性的默认值）来真实执行页面顶层代码逻辑，验证数据查询调用链和分支逻辑不报错。这验证的是"代码执行路径"，不是"真实UI渲染效果"——这个局限在`docs/TEST_REPORT.md`里有明确说明。

业务逻辑层（`services/`、`repositories/`）的66个单元测试不依赖任何mock，直接用真实SQLite临时数据库执行，这部分的测试结果是完全真实的。
