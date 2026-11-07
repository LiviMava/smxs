"""生成YApi原生JSON和可读接口文档；仅使用Python标准库。"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def s(desc, limit=1000, **kw):
    return dict(type='string', description=desc, maxLength=limit, **kw)

def enum(desc, values):
    return s(desc, enum=values.split('|'))

def obj(props, required=()):
    return dict(type='object', properties=props, required=list(required), additionalProperties=False)

def arr(item, **kw):
    return dict(type='array', items=item, **kw)

def integer(desc, minimum=0):
    return dict(type='integer', description=desc, minimum=minimum)

ID = s('稳定ID，字符串；不得用姓名作为关联键', 64, minLength=1)
UUID = s('问题模块UUID，数据库UUID类型，对外标准UUID字符串', 36, minLength=36, format='uuid')
TIME = s('ISO8601带时区时间，例如2026-11-09T09:00:00+08:00', format='date-time')
VER = integer('客户端读取到的当前版本；成功业务写入递增', 1)
STATUS = enum('编制中/待回复/已回复/已关闭', 'DRAFT|PENDING_REPLY|REPLIED|CLOSED')
SEVERITY = enum('等级含义及S级阻断规则待业务确认', 'S|A|B|C')
SYNC = enum('TC状态独立于问题业务状态', 'NOT_SYNCED|PENDING|SUCCESS|FAILED')
BOOL = dict(type='boolean')
ATTIDS = arr(UUID, maxItems=10, uniqueItems=True, description='仅本问题、本人上传、CLEAN且TEMP的附件ID；事务内绑定')
ACTION = enum('当前用户允许的业务操作，服务端计算', 'EDIT|SUBMIT|REPLY|CONFIRM|TRANSFER|REOPEN|DELETE|UPLOAD|RETRY_SYNC')

def nullable(schema):
    return {'anyOf': [schema, {'type': 'null'}]}

attachment = obj(dict(id=UUID, fileName=s('原文件名',255), contentType=s('实际检测MIME类型',128),
    sizeBytes=integer('文件大小，字节',1), purpose=enum('用途','SCREENSHOT|REPLY'),
    state=enum('状态','TEMP|BOUND|DELETED'), scanStatus=enum('扫描结果','PENDING|CLEAN|REJECTED'),
    createdAt=TIME), ['id','fileName','contentType','sizeBytes','purpose','state','scanStatus','createdAt'])
summary = obj(dict(id=UUID, issueNo=s('问题编号',64), title=s('概述',100), severity=nullable(SEVERITY), status=STATUS,
    reviewId=ID, roomId=ID, roomNo=s('房间编号',100), baselineId=nullable(ID), baselineNo=nullable(s('基线编号',128)),
    reportId=nullable(ID), reportName=nullable(s('报告名',255)), raiserId=ID, raiserName=s('提出人姓名',100),
    handlerId=nullable(ID), handlerName=nullable(s('处理人姓名',100)), tcSyncStatus=SYNC, version=VER,
    updatedAt=TIME, allowedActions=arr(ACTION)), ['id','issueNo','title','severity','status','reviewId','roomId','roomNo',
    'baselineId','baselineNo','reportId','reportName','raiserId','raiserName','handlerId','handlerName','tcSyncStatus','version','updatedAt','allowedActions'])
detail = obj({**summary['properties'], 'description':nullable(s('问题描述',10000)),
    'suggestedSolution':nullable(s('建议方案',10000)), 'sourceType':enum('来源','ANNOTATION|ROOM|IMPORT'),
    'annotationId':nullable(ID), 'modelVersion':nullable(s('数模版本',64)), 'createdAt':TIME,
    'submittedAt':nullable(TIME), 'closedAt':nullable(TIME), 'attachments':arr(attachment)}, summary['required']+
    ['description','suggestedSolution','sourceType','annotationId','modelVersion','createdAt','submittedAt','closedAt','attachments'])
record = obj(dict(id=UUID, issueVersion=VER, actionType=enum('操作','CREATE|EDIT|SUBMIT|REPLY|CONFIRM|TRANSFER|REOPEN|DELETE'),
    fromStatus=nullable(STATUS), toStatus=STATUS, operatorId=ID, operatorName=s('操作者',100),
    adopted=nullable(BOOL), modificationCompleted=nullable(BOOL), handlingOpinion=nullable(enum('意见','ACCEPTABLE|RECTIFY')),
    rejectionReason=nullable(s('不采纳原因')), body=nullable(s('说明')), resolved=nullable(BOOL),
    fromHandlerId=nullable(ID), toHandlerId=nullable(ID),
    changes=arr(obj(dict(field=s('字段名'),before=nullable(s('变更前文本',10000)),after=nullable(s('变更后文本',10000))),['field','before','after'])),
    attachments=arr(attachment), createdAt=TIME), ['id','issueVersion','actionType','operatorId','operatorName','createdAt','attachments'])
result = obj(dict(id=UUID, version=VER, status=STATUS, tcSyncStatus=SYNC), ['id','version','status','tcSyncStatus'])
counts = obj({k:integer('同一数据权限和筛选下的问题去重数量') for k in ['todo','done','all']}, ['todo','done','all'])

def page(item):
    return obj(dict(page=integer('页码，从1开始',1),pageSize=integer('页大小1..100',1),total=integer('总数'),items=arr(item)), ['page','pageSize','total','items'])

def envelope(data):
    return obj(dict(code=s('OK或业务错误码',64),message=s('结果说明'),traceId=s('追踪ID',64),data=nullable(data)), ['code','message','traceId','data'])

common = '''评审稿v0.2，所有规则为待确认设计。认证上下文取得用户、租户、组织授权；不信任客户端身份。
所有查询及文件下载同时校验租户、项目/房间授权和参与者权限。无权访问对象按404处理。
写接口要求Idempotency-Key；同键同请求重放原结果，同键异请求409。更新必须带version；冲突409且不产生历史/通知/TC事件。
HTTP 200成功；400参数错误，401未认证，403无操作权限，404不可见/不存在，409版本/状态/幂等冲突，413文件过大，415文件类型不支持，422业务规则不满足，503依赖暂不可用。
错误响应：{"code":"ISSUE_VERSION_CONFLICT","message":"数据已更新，请刷新","traceId":"示例追踪ID","data":null}。
业务提交成功仅代表本地事务成功，tcSyncStatus=PENDING表示等待异步同步，不等于TC已成功。
'''
cats = [{'name':'问题管理-分工内核心','desc':'查询、详情、编辑、处理、附件、转交；处理拆为回复和确认','list':[]},
        {'name':'问题管理-依赖及待确认扩展','desc':'补齐闭环所需；责任边界需评审确认，不代表本期已承诺','list':[]}]

def add(title, method, path, description, response, body=None, query=None, form=None, extra=False):
    headers=[dict(name='Authorization',value='Bearer {{token}}',required='1',desc='统一认证令牌，方案待对接')]
    if method not in ['GET']:
        headers.append(dict(name='Idempotency-Key',value='',example='6acfb834-2b83-4ec1-9c34-2668c86f0112',required='1',desc='每次新操作生成唯一键，网络重试复用，最多64字符；保存7天'))
    if body:
        headers.append(dict(name='Content-Type',value='application/json',required='1'))
    md=description+'\n\n'+common
    api=dict(title=title, method=method,path='/api/v1'+path,status='undone',type='static',tag=['v0.2评审稿'],
        desc='<pre>'+md+'</pre>',markdown=md,req_headers=headers,req_params=[dict(name=n,desc='路径对象ID',example='5b591019-f732-4f43-8121-a4313e1e3787') for n in re.findall(r'\{(\w+)\}',path)],
        req_query=query or [],req_body_type='form' if form else 'json',req_body_form=form or [],
        req_body_is_json_schema=bool(body),req_body_other=json.dumps(body,ensure_ascii=False) if body else '',
        res_body_type='json',res_body_is_json_schema=True,res_body=json.dumps(envelope(response),ensure_ascii=False),
        api_opened=False,index=sum(len(c['list']) for c in cats))
    cats[int(extra)]['list'].append(api)

def q(name,desc,example='',required=False):
    return dict(name=name,desc=desc,example=str(example),required='1' if required else '0')

filters=[q('keyword','问题编号或概述包含匹配，最多100字符；转义LIKE通配符'),q('baselineNo','基线编号包含匹配，最多128字符'),
    q('roomNo','房间编号包含匹配，最多100字符'),q('status','DRAFT/PENDING_REPLY/REPLIED/CLOSED'),q('severity','S/A/B/C'),q('projectId','已授权项目ID，不扩大权限')]
paging=[q('page','正整数，默认1',1),q('pageSize','1..100，默认20',20)]
add('分页查询问题列表','GET','/issues','bucket默认TODO。TODO=当前角色有待执行动作；DONE=历史参与且当前无待执行动作；ALL=授权范围内曾参与问题。DONE不等于CLOSED。固定updatedAt DESC,id DESC排序。counts复用筛选但不受bucket及分页影响。',
    obj({**page(summary)['properties'],'counts':counts},page(summary)['required']+['counts']),
    query=[q('bucket','TODO/DONE/ALL，默认TODO','TODO')]+filters+paging)
add('查询问题详情','GET','/issues/{issueId}','返回基本信息和当前有效SCREENSHOT附件；回复附件通过处理记录返回。处理记录独立分页，避免详情无限增长。',detail)
add('查询处理记录','GET','/issues/{issueId}/actions','按issueVersion ASC分页，包含全部轮次回复、退回、转交、激活和字段变更；同步错误供运维查询，不混充业务操作。',page(record),query=paging)
add('编辑问题基本信息','PATCH','/issues/{issueId}',
    'DRAFT仅提出人可修改title/severity/description/suggestedSolution/handlerId/screenshotAttachmentIds；PENDING_REPLY仅当前处理人可改建议方案和截图；REPLIED仅提出人可改描述、建议方案、截图。CLOSED禁止编辑。未传字段保持原值；空字符串用于清空可选建议方案，截图数组为最终集合（可保留已有BOUND截图），空数组移除全部；不可移除历史回复附件。越权字段返回422，不得静默忽略。保存不推进状态，至少一个业务字段。',result,
    obj(dict(version=VER,title=s('概述',100,minLength=1),severity=SEVERITY,description=s('问题描述',10000,minLength=1),suggestedSolution=s('建议方案',10000),handlerId=ID,screenshotAttachmentIds=ATTIDS),['version']))
add('处理人提交回复','POST','/issues/{issueId}/replies',
    '仅PENDING_REPLY的当前处理人。adopted=true时modificationCompleted及handlingOpinion必填；false时rejectionReason非空必填，modificationCompleted/handlingOpinion必须省略。body选填最多300字符。提交后REPLIED，待提出人确认；即使未整改完成也可回复，是否允许关闭由提出人判断（待确认）。每轮回复独立保存。',result,
    obj(dict(version=VER,adopted=BOOL,modificationCompleted=BOOL,handlingOpinion=enum('处理意见','ACCEPTABLE|RECTIFY'),rejectionReason=s('不采纳理由',1000,minLength=1),body=s('处理说明',300),attachmentIds=ATTIDS),['version','adopted']))
add('提出人确认或退回','POST','/issues/{issueId}/confirmations',
    '仅REPLIED的提出人。resolved=true转CLOSED，effective suggestedSolution（本次非空值或已存值）必须非空；false转PENDING_REPLY，comment非空必填。suggestedSolution省略保留原值；关闭不是处理人自报完成。关闭未采纳问题是否例外待确认。',result,
    obj(dict(version=VER,resolved=BOOL,comment=s('评审意见',1000),suggestedSolution=s('建议方案',10000)),['version','resolved']))
add('上传问题附件','POST','/issues/{issueId}/attachments',
    'multipart/form-data，由客户端生成boundary。SCREENSHOT仅与编辑权限一致；REPLY仅PENDING_REPLY当前处理人。单文件20MiB、每次绑定最多10个（拟定），截图PNG/JPEG，回复附件PNG/JPEG/PDF/DOCX/XLSX（拟定）；服务端校验真实类型及扫描。上传成功仅TEMP不改变问题状态/版本；CLEAN后才能绑定，24小时未绑定清理。',attachment,
    form=[dict(name='file',type='file',required='1',desc='单个文件'),dict(name='purpose',type='text',required='1',example='REPLY',desc='SCREENSHOT或REPLY')])
add('获取附件状态和元数据','GET','/issues/{issueId}/attachments/{attachmentId}',
    '用于查询异步扫描结果。TEMP仅上传人可读；BOUND按问题权限可读；附件必须属于路径问题且未删除。',attachment)
add('获取附件下载地址','GET','/issues/{issueId}/attachments/{attachmentId}/download-url',
    '仅CLEAN且BOUND附件；重新校验问题及附件权限，返回有效期60秒签名URL（拟定），禁止永久公开链接，记录下载审计。',
    obj(dict(url=s('短期签名URL',4096,format='uri'),expiresAt=TIME),['url','expiresAt']))
add('转交问题','POST','/issues/{issueId}/transfers',
    '仅PENDING_REPLY当前处理人。targetHandlerId必须有效、具有同一项目/房间访问及处理资格，且不等于当前处理人。reason选填符合原型。原处理人历史参与关系保留，新处理人加入；状态不变，原处理人进入DONE（若同时仍有其他角色待办则以TODO优先）；新处理人TODO。同事务产生转交通知和TC同步事件。',result,
    obj(dict(version=VER,targetHandlerId=ID,reason=s('转交原因',1000)),['version','targetHandlerId']))
add('房间创建问题草稿','POST','/issues',
    '依赖接口，需与评审房间负责人明确由谁实现。仅有房间提问权限者。总是创建DRAFT；提出人/项目/事业部/对象名称快照均由服务端推导。sourceType=ANNOTATION要求annotationId且sourceRef等于批注ID；ROOM人工创建要求唯一sourceRef。校验房间、评审单、基线、批注归属一致。提交另调submit。sourceRef重复同内容返回已有结果，异内容409；IMPORT由后续导入流程使用，不开放本接口。',result,
    obj(dict(title=s('概述',100,minLength=1),roomId=ID,reviewId=ID,baselineId=ID,reportId=ID,annotationId=ID,
    sourceType=enum('来源','ANNOTATION|ROOM'),sourceRef=s('来源幂等键',128,minLength=1),severity=SEVERITY,handlerId=ID,
    description=s('描述',10000),suggestedSolution=s('建议方案',10000)),['title','roomId','reviewId','sourceType','sourceRef']),extra=True)
add('提交问题草稿','POST','/issues/{issueId}/submit',
    '依赖接口：仅DRAFT提出人，校验概述、等级、描述、处理人、房间/评审单有效及访问授权后转PENDING_REPLY。写首次submittedAt，产生TC及通知事件。提出人与处理人是否允许同人待确认。',result,obj(dict(version=VER),['version']),extra=True)
add('激活已关闭问题','POST','/issues/{issueId}/reopen',
    '待确认扩展：暂定CLOSED的提出人或当前处理人可激活；转PENDING_REPLY，清空closedAt，不覆盖历史结论，保留当前处理人；校验处理人仍有效。reason选填按原型。',result,obj(dict(version=VER,reason=s('激活说明',1000)),['version']),extra=True)
add('删除草稿','POST','/issues/{issueId}/delete',
    '待确认扩展：仅DRAFT提出人逻辑删除，version递增，写DELETE历史；不物理删除历史、不复用编号。已提交问题禁止删除。',result,obj(dict(version=VER),['version']),extra=True)
add('重试TC同步','POST','/issues/{issueId}/tc-sync/retry',
    '待确认扩展：仅具有issue:sync:retry权限且问题可见用户；当前tcSyncStatus=FAILED。重排失败outbox事件，保留事件ID及业务版本，不生成重复TC对象。只更新同步元数据，不递增业务版本、不新写业务动作；与同步worker采用行锁协调。',result,obj(dict(version=VER),['version']),extra=True)

(ROOT/'yapi.json').write_text(json.dumps(cats,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# 问题管理接口文档 v0.2\n','> 2026-11-07，评审稿；由 generate_contract.py 与 yapi.json 同源生成。\n',
       '## 通用约定\n',common,'所有ID为字符串；时间为ISO8601；空值使用null，数组无结果返回[]。请求禁止未声明字段。\n',
       'JSON Schema中的条件必填请同时阅读业务说明，服务端必须实现；本稿不把条件规则简化成全部字段必填。\n',
       '## 接口目录\n','|分类|方法|路径|名称|\n|---|---|---|---|']
for c in cats:
    for a in c['list']:
        lines.append(f"|{c['name']}|{a['method']}|`{a['path']}`|{a['title']}|")
for c in cats:
    for a in c['list']:
        lines += [f"\n## {a['title']}\n",f"`{a['method']} {a['path']}`\n",a['markdown'].split('\n\n评审稿')[0]]
        if a['req_query']:
            lines += ['\n|查询字段|要求|示例|\n|---|---|---|']+[f"|{q['name']}|{q['desc']}|{q['example']}|" for q in a['req_query']]
        if a['req_body_form']:
            lines += ['\n请求表单：\n```json\n'+json.dumps(a['req_body_form'],ensure_ascii=False,indent=2)+'\n```']
        if a['req_body_other']:
            lines += ['\n请求 JSON Schema：\n```json\n'+json.dumps(json.loads(a['req_body_other']),ensure_ascii=False,indent=2)+'\n```']
        lines += ['\n响应 JSON Schema：\n```json\n'+json.dumps(json.loads(a['res_body']),ensure_ascii=False,indent=2)+'\n```']
(ROOT/'接口文档.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'Generated {sum(len(c["list"]) for c in cats)} APIs')
