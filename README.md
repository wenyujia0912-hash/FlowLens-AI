# FlowLens AI

B2B 智能履约与运营分析平台 · 个人独立作品集项目

> 全部数据均为独立构造的模拟数据，不代表任何真实企业系统，不引用、不复刻任何实习或工作中接触的真实客户、订单、内部文档、系统截图或业务规则。

## 项目背景

B2B 电商/企业采购平台的订单履约涉及客户、供应商、物流等多个环节，问题可能分散在不同数据源中。人工筛选和交叉核对容易造成发现延迟或遗漏；发现异常后，如果没有统一的任务记录，处理责任、进度和结果也不容易追踪。

FlowLens AI 是围绕这个问题做的一个闭环系统：**规则引擎负责确定性地发现异常，AI 负责在事实基础上做解释和建议，人工始终是最终决策者**。系统把"发现问题"和"处理问题"两件事串起来，而不是只给一个异常列表就结束。

## 目标用户

| 角色 | 主要目标 |
|---|---|
| 运营专员 | 发现异常并推动解决——查看异常、分析背景、更新处理进度 |
| 运营主管 | 掌握整体风险并分配工作——查看高风险订单、任务积压、处理时效 |
| 业务管理人员 | 观察履约表现并识别改进方向——查看趋势、异常分布、周期复盘 |

## 核心业务闭环

```
生成模拟数据 → 规则引擎扫描异常 → 查看事实依据 → AI诊断（Mock）
    → 人工核实/采纳/拒绝 → 创建运营任务 → 处理记录+状态流转
    → 完成任务（必填处理结果） → 驾驶舱/分析页统计实时更新
```

这个闭环里，**AI 只出现在"诊断"这一步，且只产出建议**——它不会自动创建任务，不会修改任何订单/异常状态，所有写操作都需要人工在界面上明确触发。

## 核心功能

- **运营驾驶舱**：订单总量、异常订单数、待处理异常、履约完成率、逾期任务数，均为数据库实时聚合；点击任意卡片跳转到对应筛选列表
- **客户与订单管理**：客户/订单列表与详情，客户详情里的订单数、异常数由数据库关联查询计算，不使用静态数字
- **AI 异常诊断中心**：五种规则（超时未发货、物流延迟、履约超时、供应商备货异常、订单状态冲突）+ Mock AI 诊断，诊断结果严格分四区展示（已知事实 / AI推测 / 建议操作 / 待核实事项），支持重新分析、人工改风险等级、从诊断创建任务
- **运营任务中心**：任务创建、状态流转（待处理→处理中→已完成/已取消）、处理记录时间线（追加式，不覆盖历史）、完成任务强制要求填写处理结果
- **运营分析**：履约/异常/任务三个维度的统计图表 + 明细查看 + Excel导出

## 技术栈

| 层次 | 技术 | 备注 |
|---|---|---|
| Web UI | Streamlit | 页面、导航、表单 |
| 业务逻辑 | Python 3.9+ | 服务层（services/）+ 数据访问层（repositories/）分离 |
| 数据库 | SQLite（标准库 `sqlite3`） | 单文件，无需额外部署数据库服务 |
| 可视化 | Plotly | 趋势图、分布图 |
| Excel导出 | 标准库 `zipfile`（见下方"已知限制"） | 当前未依赖pandas/openpyxl |
| AI 服务 | Mock AI（当前唯一模式） | 统一接口设计，预留真实LLM接入点，**当前未接入、不产生费用** |

## 本地运行

### 1. 创建虚拟环境并安装依赖

```bash
cd flowlens-ai
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

> ⚠️ **依赖安装尚未在真实网络环境下验证**（开发过程中网络环境受限）。
> `streamlit`/`plotly`/`pandas`/`openpyxl` 均未实际安装运行过，这是本项目
> 当前最大的已知限制，详见下方"已知限制"。首次安装后请执行"启动验收清单"
> 逐项确认。

### 2. 配置环境变量（可选）

```bash
cp .env.example .env
# 默认配置即可运行，AI_MODE=mock 不需要填写任何API Key
```

### 3. 生成模拟数据

```bash
python -m database.seed_data
```

重复运行是安全的（检测到已有数据会跳过，不产生重复记录）。如需重新生成：

```bash
python -m database.seed_data --force
```

验证数据完整性：

```bash
python -m database.validate
```

### 4. 启动应用

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`，左侧导航进入五个模块。

### 5. 运行测试

```bash
python -m unittest discover -s tests
```

当前共 **66 个单元测试**，详见 [docs/TEST_REPORT.md](docs/TEST_REPORT.md)。

## 项目目录结构

```
flowlens-ai/
├── app.py                        # Streamlit 入口 + 启动自检
├── config/
│   ├── settings.py               # 环境变量读取
│   └── anomaly_rules.py          # 异常规则阈值集中配置
├── pages/
│   ├── 01_dashboard.py           # 运营驾驶舱
│   ├── 02_customers_orders.py    # 客户与订单
│   ├── 03_anomaly_center.py      # AI 异常诊断中心
│   ├── 04_task_center.py         # 运营任务中心
│   └── 05_analytics.py           # 运营分析
├── components/                   # 可复用UI组件（布局/筛选/徽章/KPI卡片）
├── services/                     # 业务逻辑：规则引擎、AI诊断、任务流转、统计、导出
├── repositories/                 # 数据访问层（只做SQL读写，不含业务判断）
├── models/schemas.py             # 跨层数据结构定义
├── database/
│   ├── connection.py             # SQLite连接管理
│   ├── schema.sql                # 业务表结构
│   ├── seed_data.py              # 模拟数据生成（可复现）
│   └── validate.py               # 数据完整性校验
├── tests/                        # 66个单元测试
├── docs/                         # 本次交付的说明文档（见下方清单）
├── exports/                      # Excel导出文件输出目录
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## 环境变量说明

见 `.env.example`。

| 变量 | 说明 | 默认值 |
|---|---|---|
| `APP_ENV` | 运行环境标识 | `local` |
| `DATABASE_PATH` | SQLite 文件路径 | `database/flowlens.db` |
| `AI_MODE` | AI 服务模式（当前只支持 `mock`） | `mock` |
| `AI_API_KEY` | 真实大模型 API Key（当前未使用） | 空 |
| `DEMO_MODE` | 云端演示模式标识（当前未实现对应行为） | `false` |

**不得将真实 API Key 写入 `.env` 之外的任何文件或提交到版本库**（`.env` 已在 `.gitignore` 中排除）。

## 项目文档

- [docs/PRODUCT.md](docs/PRODUCT.md) —— 产品说明：业务流程、功能模块、AI能力与人机协同机制
- [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) —— 5-8分钟演示脚本
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) —— 技术架构：模块划分、数据流转、Mock AI设计、真实AI扩展方式
- [docs/TEST_REPORT.md](docs/TEST_REPORT.md) —— 测试报告：覆盖范围、结果、未覆盖部分
- [docs/DELIVERY_CHECK.md](docs/DELIVERY_CHECK.md) —— 交付检查清单

## 开发阶段完成情况

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 需求确认 | 理解PRD/交互/架构三份文档，输出歧义清单 | ✅ |
| 1 项目骨架 | 目录结构、导航、配置、数据库连接 | ✅ |
| 2 模拟数据 | 建表、种子脚本、完整性校验 | ✅ |
| 3 核心业务服务 | 规则引擎、异常/任务/统计服务、单元测试 | ✅ |
| 4 页面模块 | 驾驶舱、客户订单页接入真实数据 | ✅ |
| 5 AI Mock诊断 | 统一诊断接口、四区分离展示、人工确认流程 | ✅ |
| 6 闭环联调 | 任务中心页面、跨页面跳转、扫描入口 | ✅ |
| 6.5 运营分析 | 三维度统计、Excel导出 | ✅ |
| 7 测试与优化 | 系统性测试，发现并修复真实缺陷 | ✅ |
| 8 可选真实AI | 接入真实LLM API | **暂缓**（当前优先控制成本，Mock AI已验证稳定） |
| 9 演示交付 | README、产品说明、演示脚本、测试报告 | ✅ 当前阶段 |

## 已知限制

1. **真实浏览器渲染从未被验证**。开发环境网络受限，无法安装 `streamlit`/`plotly`/`pandas`/`openpyxl`。所有功能验证均通过"真实 SQLite 数据库 + 真实业务逻辑执行 + 最小化模拟 Streamlit API 调用"的方式完成——这确认了数据查询、业务规则、状态流转的正确性，但**不能**确认真实浏览器里的视觉效果、组件交互手感。首次在有网络的环境运行时，请按下方"启动验收清单"逐项确认。
2. **Excel导出不依赖 pandas/openpyxl**，改用标准库 `zipfile` 手写 OOXML 格式实现（见 `services/export_service.py` 顶部说明）。已用 `unzip`、`xml.etree.ElementTree`、macOS 系统 `file` 命令三种独立方式验证生成文件结构有效，但未能用真实 Excel/Numbers 应用完成人工打开验证（该路径被GUI自动化环境限制卡住）。网络恢复后，可选择迁移到 `pandas.DataFrame.to_excel()`，代码更简洁。
3. **真实LLM API未接入**，`services/ai_service.py` 的 `RealAIProvider` 尚未实现（`model_type="real"` 会显式报错，不会静默降级）。
4. **数据生成时间基准为动态相对时间**（见 `database/seed_data.py` 的 `_reference_now()`），不同天生成的数据库文件内容不完全相同（但同一天内多次生成完全一致）。这是为了让"扫描新异常"功能基于真实当前时间判断时结果正确，是刻意的设计取舍，不是bug。

## 启动验收清单

首次在有网络的环境运行本项目时，请按顺序确认：

- [ ] `pip install -r requirements.txt` 成功，无版本冲突
- [ ] `python -m database.seed_data` 成功生成数据，输出条数符合预期
- [ ] `python -m database.validate` 全部13项检查通过
- [ ] `python -m unittest discover -s tests` 66个测试全部通过
- [ ] `streamlit run app.py` 成功启动，浏览器正常打开
- [ ] 左侧导航五个模块均可点击进入，无报错
- [ ] 按 [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) 走一遍完整演示流程
