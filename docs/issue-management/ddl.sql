-- 问题管理 PostgreSQL 版 v0.2 评审稿，2026-11-07
-- 用户已确认PostgreSQL；语法按14+兼容设计，实际部署版本待确认。
-- 在UTF8编码的空测试库、已选定schema执行；不创建数据库、不删除已有表。
-- 本模块ID及关联键使用UUID，应用生成；外部系统ID仍为VARCHAR(64)。无需安装扩展。
-- TIMESTAMPTZ(3)保存时间点，API输出带时区ISO8601；连接池会话建议统一UTC。
-- CHECK用于静态约束；权限、跨行状态、附件归属、关联对象一致性必须由服务事务校验。
-- 标识符未加双引号，按PostgreSQL小写命名。整份脚本事务执行，任一步失败应回滚。
BEGIN;
SET LOCAL TIME ZONE 'UTC';

CREATE TABLE im_issue (
  id UUID NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  org_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  issue_no VARCHAR(64) NOT NULL,
  title VARCHAR(100) NOT NULL,
  severity VARCHAR(1) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
  description TEXT NULL,
  suggested_solution TEXT NULL,
  source_type VARCHAR(20) NOT NULL,
  source_ref VARCHAR(128) NULL,
  review_id VARCHAR(64) NOT NULL,
  room_id VARCHAR(64) NOT NULL,
  room_no VARCHAR(100) NOT NULL,
  baseline_id VARCHAR(64) NULL,
  baseline_no VARCHAR(128) NULL,
  model_version VARCHAR(64) NULL,
  report_id VARCHAR(64) NULL,
  report_name VARCHAR(255) NULL,
  annotation_id VARCHAR(64) NULL,
  raiser_id VARCHAR(64) NOT NULL,
  raiser_name VARCHAR(100) NOT NULL,
  handler_id VARCHAR(64) NULL,
  handler_name VARCHAR(100) NULL,
  tc_uid VARCHAR(128) NULL,
  tc_sync_status VARCHAR(16) NOT NULL DEFAULT 'NOT_SYNCED',
  tc_synced_version BIGINT NOT NULL DEFAULT 0,
  version BIGINT NOT NULL DEFAULT 1,
  submitted_at TIMESTAMPTZ(3) NULL,
  closed_at TIMESTAMPTZ(3) NULL,
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_by VARCHAR(64) NOT NULL,
  updated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  deleted_at TIMESTAMPTZ(3) NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_issue_no UNIQUE (tenant_id, issue_no),
  CONSTRAINT uk_issue_source UNIQUE (tenant_id, source_type, source_ref),
  CONSTRAINT uk_issue_tc UNIQUE (tenant_id, tc_uid),
  CONSTRAINT ck_issue_status CHECK (status IN ('DRAFT','PENDING_REPLY','REPLIED','CLOSED')),
  CONSTRAINT ck_issue_severity CHECK (severity IS NULL OR severity IN ('S','A','B','C')),
  CONSTRAINT ck_issue_source CHECK (source_type IN ('ANNOTATION','ROOM','IMPORT')),
  CONSTRAINT ck_issue_sync CHECK (tc_sync_status IN ('NOT_SYNCED','PENDING','SUCCESS','FAILED')),
  CONSTRAINT ck_issue_version CHECK (version >= 1 AND tc_synced_version >= 0),
  CONSTRAINT ck_issue_submitted CHECK (status = 'DRAFT' OR (severity IS NOT NULL AND handler_id IS NOT NULL AND description IS NOT NULL AND CHAR_LENGTH(TRIM(description)) > 0)),
  CONSTRAINT ck_issue_closed CHECK ((status = 'CLOSED' AND closed_at IS NOT NULL) OR (status <> 'CLOSED' AND closed_at IS NULL)),
  CONSTRAINT ck_issue_delete CHECK (deleted_at IS NULL OR status = 'DRAFT')
);
COMMENT ON TABLE im_issue IS '问题当前快照';
COMMENT ON COLUMN im_issue.id IS '应用生成UUID，接口字符串';
COMMENT ON COLUMN im_issue.tenant_id IS '从认证上下文取得';
COMMENT ON COLUMN im_issue.org_id IS '归属事业部';
COMMENT ON COLUMN im_issue.project_id IS '归属项目';
COMMENT ON COLUMN im_issue.issue_no IS '业务编号，编号规则待确认，不得MAX+1';
COMMENT ON COLUMN im_issue.title IS '问题概述';
COMMENT ON COLUMN im_issue.severity IS 'S/A/B/C，草稿可空';
COMMENT ON COLUMN im_issue.status IS 'DRAFT/PENDING_REPLY/REPLIED/CLOSED';
COMMENT ON COLUMN im_issue.description IS '问题描述，应用限制10000字符';
COMMENT ON COLUMN im_issue.suggested_solution IS '建议方案，应用限制10000字符';
COMMENT ON COLUMN im_issue.source_type IS 'ANNOTATION/ROOM/IMPORT';
COMMENT ON COLUMN im_issue.source_ref IS '来源幂等键：批注ID或导入任务+行号；人工创建用请求键';
COMMENT ON COLUMN im_issue.review_id IS '评审单ID，外部引用';
COMMENT ON COLUMN im_issue.room_id IS '评审房间ID，外部引用';
COMMENT ON COLUMN im_issue.room_no IS '房间编号快照';
COMMENT ON COLUMN im_issue.baseline_id IS '基线稳定ID';
COMMENT ON COLUMN im_issue.baseline_no IS '基线编号快照';
COMMENT ON COLUMN im_issue.model_version IS '数模版本快照';
COMMENT ON COLUMN im_issue.report_id IS '评审报告稳定ID';
COMMENT ON COLUMN im_issue.report_name IS '报告名称快照';
COMMENT ON COLUMN im_issue.annotation_id IS '数模批注ID';
COMMENT ON COLUMN im_issue.raiser_id IS '提出人稳定ID';
COMMENT ON COLUMN im_issue.raiser_name IS '提出人姓名快照';
COMMENT ON COLUMN im_issue.handler_id IS '当前处理人ID，草稿可空';
COMMENT ON COLUMN im_issue.handler_name IS '当前处理人姓名快照';
COMMENT ON COLUMN im_issue.tc_uid IS 'TC问题对象UID';
COMMENT ON COLUMN im_issue.tc_sync_status IS 'NOT_SYNCED/PENDING/SUCCESS/FAILED';
COMMENT ON COLUMN im_issue.tc_synced_version IS 'TC已确认的最大业务版本';
COMMENT ON COLUMN im_issue.version IS '乐观锁版本，每次业务写入递增';
COMMENT ON COLUMN im_issue.submitted_at IS '首次提交时间';
COMMENT ON COLUMN im_issue.closed_at IS '最近关闭时间，激活时清空';
COMMENT ON COLUMN im_issue.deleted_at IS '仅草稿允许逻辑删除';
CREATE INDEX idx_issue_handler ON im_issue (tenant_id, handler_id, status, updated_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_issue_raiser ON im_issue (tenant_id, raiser_id, status, updated_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_issue_scope ON im_issue (tenant_id, org_id, project_id, updated_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX idx_issue_room ON im_issue (tenant_id, room_id, status);
CREATE INDEX idx_issue_baseline ON im_issue (tenant_id, baseline_no);

CREATE TABLE im_issue_action (
  id UUID NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  issue_id UUID NOT NULL,
  issue_version BIGINT NOT NULL,
  action_type VARCHAR(20) NOT NULL,
  from_status VARCHAR(20) NULL,
  to_status VARCHAR(20) NOT NULL,
  operator_id VARCHAR(64) NOT NULL,
  operator_name VARCHAR(100) NOT NULL,
  adopted BOOLEAN NULL,
  modification_completed BOOLEAN NULL,
  handling_opinion VARCHAR(16) NULL,
  rejection_reason VARCHAR(1000) NULL,
  body VARCHAR(1000) NULL,
  resolved BOOLEAN NULL,
  from_handler_id VARCHAR(64) NULL,
  to_handler_id VARCHAR(64) NULL,
  changes JSONB NULL,
  created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  CONSTRAINT uk_action_version UNIQUE (issue_id, issue_version),
  CONSTRAINT fk_action_issue FOREIGN KEY (issue_id) REFERENCES im_issue(id),
  CONSTRAINT ck_action_opinion CHECK (handling_opinion IS NULL OR handling_opinion IN ('ACCEPTABLE','RECTIFY'))
);
COMMENT ON TABLE im_issue_action IS '不可覆盖的多轮回复及操作历史';
COMMENT ON COLUMN im_issue_action.issue_version IS '完成操作后的主表版本';
COMMENT ON COLUMN im_issue_action.action_type IS 'CREATE/EDIT/SUBMIT/REPLY/CONFIRM/TRANSFER/REOPEN/DELETE';
COMMENT ON COLUMN im_issue_action.adopted IS '回复是否采纳';
COMMENT ON COLUMN im_issue_action.modification_completed IS '采纳时必填；不采纳置NULL';
COMMENT ON COLUMN im_issue_action.handling_opinion IS 'ACCEPTABLE/RECTIFY；不采纳置NULL';
COMMENT ON COLUMN im_issue_action.rejection_reason IS '不采纳时必填';
COMMENT ON COLUMN im_issue_action.body IS '回复说明最多300；确认意见/转交/激活原因最多1000';
COMMENT ON COLUMN im_issue_action.resolved IS '提出人确认是否解决';
COMMENT ON COLUMN im_issue_action.changes IS '业务字段变更前后值；不得包含文件内容/凭证';
CREATE INDEX idx_action_timeline ON im_issue_action (tenant_id, issue_id, issue_version);
CREATE INDEX idx_action_operator ON im_issue_action (tenant_id, operator_id, issue_id);

CREATE TABLE im_issue_participant (
  tenant_id VARCHAR(64) NOT NULL,
  issue_id UUID NOT NULL,
  user_id VARCHAR(64) NOT NULL,
  first_participated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  last_participated_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (issue_id, user_id),
  CONSTRAINT fk_participant_issue FOREIGN KEY (issue_id) REFERENCES im_issue(id)
);
COMMENT ON TABLE im_issue_participant IS '历史参与者，转交后保留旧处理人';
CREATE INDEX idx_participant_user ON im_issue_participant (tenant_id, user_id, issue_id);

CREATE TABLE im_issue_attachment (
  id UUID NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  issue_id UUID NOT NULL,
  action_id UUID NULL,
  purpose VARCHAR(16) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  object_key VARCHAR(512) NOT NULL,
  content_type VARCHAR(128) NOT NULL,
  size_bytes BIGINT NOT NULL,
  sha256 CHAR(64) NOT NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'TEMP',
  scan_status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  uploaded_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  expires_at TIMESTAMPTZ(3) NULL,
  bound_at TIMESTAMPTZ(3) NULL,
  deleted_at TIMESTAMPTZ(3) NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_attachment_issue FOREIGN KEY (issue_id) REFERENCES im_issue(id),
  CONSTRAINT fk_attachment_action FOREIGN KEY (action_id) REFERENCES im_issue_action(id),
  CONSTRAINT ck_attachment_size CHECK (size_bytes > 0 AND size_bytes <= 20971520),
  CONSTRAINT ck_attachment_state CHECK (state IN ('TEMP','BOUND','DELETED')),
  CONSTRAINT ck_attachment_scan CHECK (scan_status IN ('PENDING','CLEAN','REJECTED')),
  CONSTRAINT ck_attachment_purpose CHECK (purpose IN ('SCREENSHOT','REPLY'))
);
COMMENT ON TABLE im_issue_attachment IS '截图及回复附件元数据，文件在对象存储';
COMMENT ON COLUMN im_issue_attachment.action_id IS '回复附件关联操作；临时上传可空';
COMMENT ON COLUMN im_issue_attachment.purpose IS 'SCREENSHOT/REPLY';
COMMENT ON COLUMN im_issue_attachment.object_key IS '内部对象存储键，不直接对外返回';
COMMENT ON COLUMN im_issue_attachment.state IS 'TEMP/BOUND/DELETED';
COMMENT ON COLUMN im_issue_attachment.scan_status IS 'PENDING/CLEAN/REJECTED';
COMMENT ON COLUMN im_issue_attachment.expires_at IS '临时文件24小时过期，拟定';
CREATE INDEX idx_attachment_issue ON im_issue_attachment (tenant_id, issue_id, state);
CREATE INDEX idx_attachment_expiry ON im_issue_attachment (state, expires_at);

CREATE TABLE im_issue_outbox (
  id UUID NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  issue_id UUID NOT NULL,
  issue_version BIGINT NOT NULL,
  destination VARCHAR(16) NOT NULL,
  event_type VARCHAR(32) NOT NULL,
  payload JSONB NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  attempts INT NOT NULL DEFAULT 0,
  next_retry_at TIMESTAMPTZ(3) NULL,
  locked_until TIMESTAMPTZ(3) NULL,
  lock_token UUID NULL,
  last_error VARCHAR(1000) NULL,
  created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  completed_at TIMESTAMPTZ(3) NULL,
  PRIMARY KEY (id),
  CONSTRAINT uk_outbox_version UNIQUE (issue_id, issue_version, destination),
  CONSTRAINT fk_outbox_issue FOREIGN KEY (issue_id) REFERENCES im_issue(id),
  CONSTRAINT ck_outbox_status CHECK (status IN ('PENDING','PROCESSING','SUCCESS','FAILED')),
  CONSTRAINT ck_outbox_destination CHECK (destination IN ('TC','NOTIFICATION'))
);
COMMENT ON TABLE im_issue_outbox IS '业务事务内写入的TC及通知可靠事件';
COMMENT ON COLUMN im_issue_outbox.destination IS 'TC/NOTIFICATION';
COMMENT ON COLUMN im_issue_outbox.payload IS '此版本完整同步快照或通知载荷';
COMMENT ON COLUMN im_issue_outbox.status IS 'PENDING/PROCESSING/SUCCESS/FAILED';
COMMENT ON COLUMN im_issue_outbox.locked_until IS '领取任务的租约，进程崩溃后可回收';
COMMENT ON COLUMN im_issue_outbox.lock_token IS '防止过期worker覆盖新worker';
COMMENT ON COLUMN im_issue_outbox.last_error IS '脱敏错误';
CREATE INDEX idx_outbox_poll ON im_issue_outbox (status, next_retry_at, locked_until);

CREATE TABLE im_issue_idempotency (
  tenant_id VARCHAR(64) NOT NULL,
  actor_id VARCHAR(64) NOT NULL,
  request_key VARCHAR(64) NOT NULL,
  request_hash CHAR(64) NOT NULL,
  response_status INT NULL,
  response_body JSONB NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'PROCESSING',
  created_at TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  expires_at TIMESTAMPTZ(3) NOT NULL,
  PRIMARY KEY (tenant_id, actor_id, request_key),
  CONSTRAINT ck_idempotency_state CHECK (state IN ('PROCESSING','COMPLETED'))
);
COMMENT ON TABLE im_issue_idempotency IS '请求幂等，业务成功结果同事务提交';
COMMENT ON COLUMN im_issue_idempotency.request_hash IS '方法+路径+规范化请求体或文件SHA256的摘要';
COMMENT ON COLUMN im_issue_idempotency.expires_at IS '拟定保存7天，过期后不再承诺重放';
CREATE INDEX idx_idempotency_expiry ON im_issue_idempotency (expires_at);

COMMIT;
