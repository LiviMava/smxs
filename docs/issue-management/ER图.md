# 问题管理 PostgreSQL ER图

依据当前 ddl.sql（v0.2），2026-11-07。共6张表、101个字段、5条物理外键；总览省略部分字段，完整字段图保留全部列。

[PNG总览](ER图_总览.png) · [SVG矢量图](ER图_总览.svg) · [总览Mermaid源文件](ER图_总览.mmd) · [完整字段Mermaid源文件](ER图_完整字段.mmd)

## 总览

```mermaid
erDiagram
    direction LR
    im_issue ||..o{ im_issue_action : "issue_id"
    im_issue ||--o{ im_issue_participant : "issue_id"
    im_issue ||..o{ im_issue_attachment : "issue_id"
    im_issue_action |o..o{ im_issue_attachment : "action_id"
    im_issue ||..o{ im_issue_outbox : "issue_id"
    im_issue["im_issue · 问题主表"] {
        uuid id PK "应用生成UUID，接口字符串"
        varchar(64) tenant_id "租户范围"
        varchar(64) issue_no "业务编号，编号规则待确认，不得MAX+1"
        varchar(100) title "问题概述"
        varchar(20) status "DRAFT/PENDING_REPLY/REPLIED/CLOSED"
        bigint version "乐观锁版本，每次业务写入递增"
        varchar(64) raiser_id "外部逻辑引用"
        varchar(64) handler_id "外部逻辑引用 可空"
        varchar(64) room_id "外部逻辑引用"
        varchar(16) tc_sync_status "NOT_SYNCED/PENDING/SUCCESS/FAILED"
    }
    im_issue_action["im_issue_action · 处理记录"] {
        uuid id PK
        uuid issue_id FK "必填外键"
        bigint issue_version "完成操作后的主表版本"
        varchar(20) action_type "CREATE/EDIT/SUBMIT/REPLY/CONFIRM/TRANSFER/REOPEN/DELETE"
        varchar(64) operator_id "外部逻辑引用"
        boolean adopted "回复是否采纳"
        boolean resolved "提出人确认是否解决"
    }
    im_issue_participant["im_issue_participant · 历史参与者"] {
        uuid issue_id PK,FK "必填外键；联合主键成员"
        varchar(64) user_id PK "外部逻辑引用；联合主键成员"
        varchar(64) tenant_id "租户范围"
        timestamptz(3) last_participated_at
    }
    im_issue_attachment["im_issue_attachment · 问题附件"] {
        uuid id PK
        uuid issue_id FK "必填外键"
        uuid action_id FK "可空外键 0..1"
        varchar(16) purpose "SCREENSHOT/REPLY"
        varchar(16) state "TEMP/BOUND/DELETED"
        varchar(512) object_key "内部对象存储键，不直接对外返回"
    }
    im_issue_outbox["im_issue_outbox · 可靠事件"] {
        uuid id PK
        uuid issue_id FK "必填外键"
        bigint issue_version
        varchar(16) destination "TC/NOTIFICATION"
        varchar(16) status "PENDING/PROCESSING/SUCCESS/FAILED"
        jsonb payload "此版本完整同步快照或通知载荷"
    }
    im_issue_idempotency["im_issue_idempotency · 请求幂等"] {
        varchar(64) tenant_id PK "租户范围；联合主键成员"
        varchar(64) actor_id PK "外部逻辑引用；联合主键成员"
        varchar(64) request_key PK "；联合主键成员"
        char(64) request_hash "方法+路径+规范化请求体或文件SHA256的摘要"
        varchar(16) state
        jsonb response_body
    }
```

## 图例与关联含义

- `PK`为主键成员；`FK`为数据库已声明的物理外键。复合主键中的每个成员均标PK，不表示单列唯一。
- `||`为恰好一个，`o{`为零到多；附件指向处理记录一端的`|o`表示零或一个。
- 实线表示父键也是子表主键的一部分；虚线表示非标识关系。两种连线都可能是数据库物理外键，不能把虚线误读成外部引用。
- 每个问题可以有多条处理记录、历史参与者、附件和可靠事件。附件必须归属一个问题，但可不关联具体处理记录（截图、临时上传等）。
- 请求幂等表没有issue_id或问题外键，独立按租户、操作者、请求键去重；因此图中不连到问题表。

|父表|子表及外键|基数|说明|
|---|---|---|---|
|im_issue|im_issue_action.issue_id|1 → 0..N|每条操作记录必须对应一个问题|
|im_issue|im_issue_participant.issue_id|1 → 0..N|每条参与关系必须对应一个问题|
|im_issue|im_issue_attachment.issue_id|1 → 0..N|每个附件必须对应一个问题|
|im_issue_action|im_issue_attachment.action_id|0..1 ← 0..N|单个附件最多关联一条操作；单条操作可有多个附件|
|im_issue|im_issue_outbox.issue_id|1 → 0..N|每个事件必须对应一个问题|

图中的0..N依据数据库约束：外键不强制父记录至少有一条子记录。业务创建事务会同时写CREATE历史和参与者，这是应用规则。

## 唯一约束

|表|约束|联合唯一字段|
|---|---|---|
|im_issue|uk_issue_no|tenant_id, issue_no|
|im_issue|uk_issue_source|tenant_id, source_type, source_ref|
|im_issue|uk_issue_tc|tenant_id, tc_uid|
|im_issue_action|uk_action_version|issue_id, issue_version|
|im_issue_outbox|uk_outbox_version|issue_id, issue_version, destination|

可空唯一键成员遵循PostgreSQL默认语义：多条NULL不互相冲突。上述唯一约束均不能把某个成员单独视为唯一。

## 外部逻辑引用与实现约束

|字段范围|引用对象|数据库外键|
|---|---|---|
|tenant_id / org_id / project_id|租户、事业部、项目主数据|无，应用校验|
|raiser_id / handler_id / user_id / operator_id / actor_id / uploaded_by等人员字段|统一用户服务|无，应用校验|
|review_id / room_id|评审单、评审房间|无，应用校验|
|baseline_id / report_id / annotation_id|数模基线、评审报告、批注|无，应用校验|
|tc_uid|TC问题对象|无，集成服务维护|
|object_key|对象存储中的文件|无，文件服务维护|

以上均是逻辑引用，当前DDL未定义外部实体表，因此不绘制成已建物理表。
子表tenant_id与主表一致性，以及附件action_id对应操作与附件issue_id归属同一问题，由应用事务校验；当前DDL的单列外键没有强制这两项跨字段一致性。
outbox.issue_version是业务事件版本；它与处理记录的版本保持应用层一致，当前DDL没有声明指向action的复合外键。

## 完整字段图

```mermaid
erDiagram
    direction LR
    im_issue ||..o{ im_issue_action : "issue_id"
    im_issue ||--o{ im_issue_participant : "issue_id"
    im_issue ||..o{ im_issue_attachment : "issue_id"
    im_issue_action |o..o{ im_issue_attachment : "action_id"
    im_issue ||..o{ im_issue_outbox : "issue_id"
    im_issue["im_issue · 问题主表"] {
        uuid id PK "NOT NULL；应用生成UUID，接口字符串"
        varchar(64) tenant_id "NOT NULL；从认证上下文取得"
        varchar(64) org_id "NOT NULL；归属事业部"
        varchar(64) project_id "NOT NULL；归属项目"
        varchar(64) issue_no "NOT NULL；业务编号，编号规则待确认，不得MAX+1"
        varchar(100) title "NOT NULL；问题概述"
        varchar(1) severity "NULL；S/A/B/C，草稿可空"
        varchar(20) status "NOT NULL；DRAFT/PENDING_REPLY/REPLIED/CLOSED"
        text description "NULL；问题描述，应用限制10000字符"
        text suggested_solution "NULL；建议方案，应用限制10000字符"
        varchar(20) source_type "NOT NULL；ANNOTATION/ROOM/IMPORT"
        varchar(128) source_ref "NULL；来源幂等键：批注ID或导入任务+行号；人工创建用请求键"
        varchar(64) review_id "NOT NULL；评审单ID，外部引用"
        varchar(64) room_id "NOT NULL；外部逻辑引用"
        varchar(100) room_no "NOT NULL；房间编号快照"
        varchar(64) baseline_id "NULL；基线稳定ID"
        varchar(128) baseline_no "NULL；基线编号快照"
        varchar(64) model_version "NULL；数模版本快照"
        varchar(64) report_id "NULL；评审报告稳定ID"
        varchar(255) report_name "NULL；报告名称快照"
        varchar(64) annotation_id "NULL；数模批注ID"
        varchar(64) raiser_id "NOT NULL；外部逻辑引用"
        varchar(100) raiser_name "NOT NULL；提出人姓名快照"
        varchar(64) handler_id "NULL；外部逻辑引用 可空"
        varchar(100) handler_name "NULL；当前处理人姓名快照"
        varchar(128) tc_uid "NULL；TC问题对象UID"
        varchar(16) tc_sync_status "NOT NULL；NOT_SYNCED/PENDING/SUCCESS/FAILED"
        bigint tc_synced_version "NOT NULL；TC已确认的最大业务版本"
        bigint version "NOT NULL；乐观锁版本，每次业务写入递增"
        timestamptz(3) submitted_at "NULL；首次提交时间"
        timestamptz(3) closed_at "NULL；最近关闭时间，激活时清空"
        varchar(64) created_by "NOT NULL；"
        timestamptz(3) created_at "NOT NULL；"
        varchar(64) updated_by "NOT NULL；"
        timestamptz(3) updated_at "NOT NULL；"
        timestamptz(3) deleted_at "NULL；仅草稿允许逻辑删除"
    }
    im_issue_action["im_issue_action · 处理记录"] {
        uuid id PK "NOT NULL；"
        varchar(64) tenant_id "NOT NULL；"
        uuid issue_id FK "NOT NULL；必填外键"
        bigint issue_version "NOT NULL；完成操作后的主表版本"
        varchar(20) action_type "NOT NULL；CREATE/EDIT/SUBMIT/REPLY/CONFIRM/TRANSFER/REOPEN/DELETE"
        varchar(20) from_status "NULL；"
        varchar(20) to_status "NOT NULL；"
        varchar(64) operator_id "NOT NULL；外部逻辑引用"
        varchar(100) operator_name "NOT NULL；"
        boolean adopted "NULL；回复是否采纳"
        boolean modification_completed "NULL；采纳时必填；不采纳置NULL"
        varchar(16) handling_opinion "NULL；ACCEPTABLE/RECTIFY；不采纳置NULL"
        varchar(1000) rejection_reason "NULL；不采纳时必填"
        varchar(1000) body "NULL；回复说明最多300；确认意见/转交/激活原因最多1000"
        boolean resolved "NULL；提出人确认是否解决"
        varchar(64) from_handler_id "NULL；"
        varchar(64) to_handler_id "NULL；"
        jsonb changes "NULL；业务字段变更前后值；不得包含文件内容/凭证"
        timestamptz(3) created_at "NOT NULL；"
    }
    im_issue_participant["im_issue_participant · 历史参与者"] {
        varchar(64) tenant_id "NOT NULL；"
        uuid issue_id PK,FK "NOT NULL；必填外键；联合主键成员"
        varchar(64) user_id PK "NOT NULL；外部逻辑引用；联合主键成员"
        timestamptz(3) first_participated_at "NOT NULL；"
        timestamptz(3) last_participated_at "NOT NULL；"
    }
    im_issue_attachment["im_issue_attachment · 问题附件"] {
        uuid id PK "NOT NULL；"
        varchar(64) tenant_id "NOT NULL；"
        uuid issue_id FK "NOT NULL；必填外键"
        uuid action_id FK "NULL；可空外键 0..1"
        varchar(16) purpose "NOT NULL；SCREENSHOT/REPLY"
        varchar(255) file_name "NOT NULL；"
        varchar(512) object_key "NOT NULL；内部对象存储键，不直接对外返回"
        varchar(128) content_type "NOT NULL；"
        bigint size_bytes "NOT NULL；"
        char(64) sha256 "NOT NULL；"
        varchar(16) state "NOT NULL；TEMP/BOUND/DELETED"
        varchar(16) scan_status "NOT NULL；PENDING/CLEAN/REJECTED"
        varchar(64) uploaded_by "NOT NULL；"
        timestamptz(3) created_at "NOT NULL；"
        timestamptz(3) expires_at "NULL；临时文件24小时过期，拟定"
        timestamptz(3) bound_at "NULL；"
        timestamptz(3) deleted_at "NULL；"
    }
    im_issue_outbox["im_issue_outbox · 可靠事件"] {
        uuid id PK "NOT NULL；"
        varchar(64) tenant_id "NOT NULL；"
        uuid issue_id FK "NOT NULL；必填外键"
        bigint issue_version "NOT NULL；"
        varchar(16) destination "NOT NULL；TC/NOTIFICATION"
        varchar(32) event_type "NOT NULL；"
        jsonb payload "NOT NULL；此版本完整同步快照或通知载荷"
        varchar(16) status "NOT NULL；PENDING/PROCESSING/SUCCESS/FAILED"
        int attempts "NOT NULL；"
        timestamptz(3) next_retry_at "NULL；"
        timestamptz(3) locked_until "NULL；领取任务的租约，进程崩溃后可回收"
        uuid lock_token "NULL；防止过期worker覆盖新worker"
        varchar(1000) last_error "NULL；脱敏错误"
        timestamptz(3) created_at "NOT NULL；"
        timestamptz(3) completed_at "NULL；"
    }
    im_issue_idempotency["im_issue_idempotency · 请求幂等"] {
        varchar(64) tenant_id PK "NOT NULL；；联合主键成员"
        varchar(64) actor_id PK "NOT NULL；外部逻辑引用；联合主键成员"
        varchar(64) request_key PK "NOT NULL；；联合主键成员"
        char(64) request_hash "NOT NULL；方法+路径+规范化请求体或文件SHA256的摘要"
        int response_status "NULL；"
        jsonb response_body "NULL；"
        varchar(16) state "NOT NULL；"
        timestamptz(3) created_at "NOT NULL；"
        timestamptz(3) expires_at "NOT NULL；拟定保存7天，过期后不再承诺重放"
    }
```

完整图适合放大查看；精确约束表达式、索引、默认值见ddl.sql。重新生成Mermaid/SVG：`python generate_er.py`；Windows下重新生成PNG：`./render_er.ps1`。
