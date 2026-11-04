-- FlowLens AI 数据库 Schema
--
-- 来源：技术架构与数据设计说明书 §3（数据实体与关系）、§4（数据完整性与业务约束）。
-- 本文件只定义表结构与约束，不包含任何数据——数据由 database/seed_data.py 生成。
--
-- 设计要点：
--   - 所有外键使用 ON DELETE CASCADE 或 RESTRICT，视业务语义而定（见各表注释）。
--   - 时间字段统一存 ISO 8601 字符串（TEXT），例如 "2024-03-15T09:00:00"（技术方案 §4）。
--   - 金额/数量/单价使用 CHECK 约束禁止负数（技术方案 §4）。
--   - 枚举字段（状态、风险等级、优先级）使用 CHECK 约束限制取值范围，
--     取值与产品需求说明书 §6 的状态定义表严格一致。

PRAGMA foreign_keys = ON;

-- ============================================================
-- 客户
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    industry      TEXT NOT NULL,
    tier          TEXT NOT NULL CHECK (tier IN ('战略客户', '重点客户', '普通客户')),
    status        TEXT NOT NULL CHECK (status IN ('合作中', '暂停合作', '已终止')),
    created_at    TEXT NOT NULL
);

-- ============================================================
-- 供应商
-- ============================================================
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('合作中', '暂停合作', '已终止')),
    lead_time_days  INTEGER NOT NULL CHECK (lead_time_days >= 0)
);

-- ============================================================
-- 订单
-- 状态枚举来源：产品需求说明书 §6（订单主状态）
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    order_id              TEXT PRIMARY KEY,
    customer_id           TEXT NOT NULL REFERENCES customers (customer_id) ON DELETE RESTRICT,
    supplier_id           TEXT NOT NULL REFERENCES suppliers (supplier_id) ON DELETE RESTRICT,
    order_date            TEXT NOT NULL,
    amount                REAL NOT NULL CHECK (amount >= 0),
    status                TEXT NOT NULL CHECK (
        status IN ('待确认', '待发货', '运输中', '已签收', '已取消')
    ),
    expected_ship_at      TEXT NOT NULL,
    shipped_at            TEXT,
    expected_delivery_at  TEXT NOT NULL,
    delivered_at          TEXT,

    -- 【本阶段新增字段，非技术方案 §3 原文列出】
    -- SUPPLIER_PREP_DELAY 规则（产品需求 §5.4："供应商备货状态超过模拟设定
    -- 时限仍未更新"）需要一个"备货状态 + 最后更新时间"字段才能判断，但
    -- 技术方案 §3 的 orders 表字段列表中没有定义它。为了让该规则类型可以
    -- 被构造正反例数据并在阶段3被规则引擎读取，此处新增以下两个字段。
    -- 这是我在实现过程中发现的数据模型缺口，不是文档原有定义，请你确认
    -- 是否合理，或者你有其他设计意图（例如把备货状态放在单独的表里）。
    supplier_prep_status     TEXT NOT NULL CHECK (
        supplier_prep_status IN ('待备货', '备货中', '备货完成')
    ),
    supplier_prep_updated_at TEXT NOT NULL,

    -- 时间先后约束（技术方案 §4）：
    --   实际发货时间不得早于下单时间；实际签收时间不得早于发货时间。
    -- SQLite 的 CHECK 约束支持跨列比较，字符串按 ISO 8601 格式可直接比较。
    CHECK (shipped_at IS NULL OR shipped_at >= order_date),
    CHECK (delivered_at IS NULL OR shipped_at IS NOT NULL),
    CHECK (delivered_at IS NULL OR delivered_at >= shipped_at)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_supplier ON orders (supplier_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);

-- ============================================================
-- 商品明细
-- ============================================================
CREATE TABLE IF NOT EXISTS order_items (
    item_id       TEXT PRIMARY KEY,
    order_id      TEXT NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    product_name  TEXT NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    REAL NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);

-- ============================================================
-- 物流记录（订单与物流的可追踪关系：一个订单对应一条当前物流记录）
-- 状态枚举来源：产品需求说明书 §6（物流状态）
-- ============================================================
CREATE TABLE IF NOT EXISTS logistics (
    logistics_id          TEXT PRIMARY KEY,
    order_id              TEXT NOT NULL UNIQUE REFERENCES orders (order_id) ON DELETE CASCADE,
    current_status        TEXT NOT NULL CHECK (
        current_status IN ('待揽收', '运输中', '派送中', '已签收', '异常')
    ),
    last_updated_at       TEXT NOT NULL,
    estimated_delivery_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_logistics_order ON logistics (order_id);

-- ============================================================
-- 物流节点事件（追加式历史记录）
-- ============================================================
CREATE TABLE IF NOT EXISTS logistics_events (
    event_id       TEXT PRIMARY KEY,
    logistics_id   TEXT NOT NULL REFERENCES logistics (logistics_id) ON DELETE CASCADE,
    event_time     TEXT NOT NULL,
    location       TEXT NOT NULL,
    event_status   TEXT NOT NULL,
    description    TEXT
);

CREATE INDEX IF NOT EXISTS idx_logistics_events_logistics ON logistics_events (logistics_id);

-- ============================================================
-- 异常记录
-- 状态枚举来源：产品需求说明书 §6（异常状态，不与任务状态混用）
-- ============================================================
CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id     TEXT PRIMARY KEY,
    order_id       TEXT NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    anomaly_type   TEXT NOT NULL,
    detected_at    TEXT NOT NULL,
    rule_code      TEXT NOT NULL,
    severity       TEXT NOT NULL CHECK (severity IN ('高', '中', '低')),
    status         TEXT NOT NULL CHECK (
        status IN ('待确认', '处理中', '已解决', '已关闭', '误报')
    ),
    resolved_at    TEXT,

    CHECK (resolved_at IS NULL OR resolved_at >= detected_at)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_order ON anomalies (order_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies (status);
CREATE INDEX IF NOT EXISTS idx_anomalies_rule_code ON anomalies (rule_code);

-- 去重约束的支持索引：同一订单同一规则在"活跃"状态下只应存在一条。
-- 技术方案 §5 的去重策略不通过数据库唯一约束强制（因为"活跃"是状态子集，
-- 不是全部状态都要求唯一），而是由阶段 3 的服务层在插入前查询判断。
-- 此处索引仅用于加速该查询。
CREATE INDEX IF NOT EXISTS idx_anomalies_dedup_lookup ON anomalies (order_id, rule_code, status);

-- ============================================================
-- AI 诊断记录
-- causes_json / recommendations_json / verification_json 存 JSON 字符串，
-- 对应技术方案 §6 的诊断结果 JSON 结构。
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_diagnoses (
    diagnosis_id      TEXT PRIMARY KEY,
    anomaly_id        TEXT NOT NULL REFERENCES anomalies (anomaly_id) ON DELETE CASCADE,
    generated_at      TEXT NOT NULL,
    summary           TEXT NOT NULL,
    causes_json       TEXT NOT NULL,
    impact            TEXT NOT NULL,
    risk_suggestion   TEXT NOT NULL CHECK (risk_suggestion IN ('low', 'medium', 'high')),
    recommendations_json TEXT NOT NULL,
    -- 【本阶段修复】technical spec §6 要求的输出结构包含 communication_draft
    -- （沟通参考文本），但原始字段列表遗漏了这一列，导致 services/ai_service.py
    -- 生成的文案无处持久化、页面无法展示——这是一个真实的数据丢失缺陷，不是
    -- 可选的润色，故补上该列。
    communication_draft TEXT NOT NULL DEFAULT '',
    verification_json TEXT NOT NULL,
    model_type        TEXT NOT NULL CHECK (model_type IN ('mock', 'real'))
);

CREATE INDEX IF NOT EXISTS idx_ai_diagnoses_anomaly ON ai_diagnoses (anomaly_id);

-- ============================================================
-- 运营任务
-- anomaly_id / order_id 均可为空（支持手动创建一般运营任务）。
-- 状态枚举来源：产品需求说明书 §6（任务状态）
-- ============================================================
CREATE TABLE IF NOT EXISTS operation_tasks (
    task_id       TEXT PRIMARY KEY,
    anomaly_id    TEXT REFERENCES anomalies (anomaly_id) ON DELETE SET NULL,
    order_id      TEXT REFERENCES orders (order_id) ON DELETE SET NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    priority      TEXT NOT NULL CHECK (priority IN ('P1', 'P2', 'P3')),
    assignee      TEXT NOT NULL,
    due_at        TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (
        status IN ('待处理', '处理中', '已完成', '已取消')
    ),
    result        TEXT,
    created_at    TEXT NOT NULL,
    completed_at  TEXT,

    -- 已完成任务必须有完成时间和处理结果（技术方案 §4）。
    CHECK (status != '已完成' OR (result IS NOT NULL AND completed_at IS NOT NULL)),
    CHECK (completed_at IS NULL OR completed_at >= created_at)
);

CREATE INDEX IF NOT EXISTS idx_tasks_anomaly ON operation_tasks (anomaly_id);
CREATE INDEX IF NOT EXISTS idx_tasks_order ON operation_tasks (order_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON operation_tasks (status);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON operation_tasks (assignee);

-- ============================================================
-- 任务处理日志（追加式，不覆盖历史）
-- ============================================================
CREATE TABLE IF NOT EXISTS task_logs (
    log_id      TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES operation_tasks (task_id) ON DELETE CASCADE,
    action      TEXT NOT NULL,
    content     TEXT,
    created_at  TEXT NOT NULL,
    actor       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs (task_id);
