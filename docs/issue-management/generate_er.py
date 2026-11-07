"""从PostgreSQL DDL生成Mermaid ER总览、完整字段图和说明。"""
from pathlib import Path
import re
import json
from html import escape

ROOT = Path(__file__).resolve().parent
sql = (ROOT / 'ddl.sql').read_text(encoding='utf-8')
tables = {}
for name, body in re.findall(r'CREATE TABLE (\w+) \(\n(.*?)\n\);', sql, re.S):
    columns = {}
    for line in body.splitlines():
        match = re.match(r'  (\w+) (UUID|VARCHAR\(\d+\)|CHAR\(\d+\)|TIMESTAMPTZ\(3\)|TEXT|JSONB|BIGINT|BOOLEAN|INT)(.*)', line)
        if match:
            column, data_type, tail = match.groups()
            columns[column] = (data_type, 'NOT NULL' not in tail)
    primary = re.search(r'PRIMARY KEY \(([^)]+)\)', body)
    primary_keys = set(primary.group(1).replace(' ', '').split(','))
    foreign_keys = {col: (target, target_col) for col, target, target_col in re.findall(
        r'FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)', body)}
    unique_keys = re.findall(r'CONSTRAINT (\w+) UNIQUE \(([^)]+)\)', body)
    title = re.search(rf"COMMENT ON TABLE {name} IS '([^']*)';", sql).group(1)
    tables[name] = dict(columns=columns, pk=primary_keys, fk=foreign_keys, unique=unique_keys, title=title)

comments = {(table, col): text for table, col, text in re.findall(
    r"COMMENT ON COLUMN (\w+)\.(\w+) IS '([^']*)';", sql)}
aliases = {
    'im_issue': '问题主表',
    'im_issue_action': '处理记录',
    'im_issue_participant': '历史参与者',
    'im_issue_attachment': '问题附件',
    'im_issue_outbox': '可靠事件',
    'im_issue_idempotency': '请求幂等',
}
overview = {
    'im_issue': ['id','tenant_id','issue_no','title','status','version','raiser_id','handler_id','room_id','tc_sync_status'],
    'im_issue_action': ['id','issue_id','issue_version','action_type','operator_id','adopted','resolved'],
    'im_issue_participant': ['issue_id','user_id','tenant_id','last_participated_at'],
    'im_issue_attachment': ['id','issue_id','action_id','purpose','state','object_key'],
    'im_issue_outbox': ['id','issue_id','issue_version','destination','status','payload'],
    'im_issue_idempotency': ['tenant_id','actor_id','request_key','request_hash','state','response_body'],
}

def diagram(full):
    lines = ['erDiagram', '    direction LR']
    for table, data in tables.items():
        for column, (target, target_col) in data['fk'].items():
            # 父实体端0..1表示子表外键可空；父实体可拥有0..N条子记录。
            parent = '|o' if data['columns'][column][1] else '||'
            link = '--' if column in data['pk'] else '..'
            lines.append(f'    {target} {parent}{link}o{{ {table} : "{column}"')
    for table, data in tables.items():
        lines.append(f'    {table}["{table} · {aliases[table]}"] {{')
        selected = data['columns'] if full else overview[table]
        for column in selected:
            dtype, nullable = data['columns'][column]
            keys = ','.join(key for key, cond in [('PK',column in data['pk']),('FK',column in data['fk'])] if cond)
            note = comments.get((table, column), '')
            if column in data['fk']:
                note = '可空外键 0..1' if nullable else '必填外键'
            elif column in ['raiser_id','handler_id','room_id','user_id','operator_id','actor_id']:
                note = '外部逻辑引用' + (' 可空' if nullable else '')
            if not full and column == 'tenant_id':
                note = '租户范围'
            if full:
                note = ('NULL；' if nullable else 'NOT NULL；') + note
            if column in data['pk'] and len(data['pk']) > 1:
                note += '；联合主键成员'
            note = note.replace('"', "'").replace('\n',' ')
            # Mermaid类型保留PostgreSQL精度/长度信息。
            lines.append(f'        {dtype.lower()} {column}' + (f' {keys}' if keys else '') + (f' "{note}"' if note else ''))
        lines.append('    }')
    return '\n'.join(lines) + '\n'

assert len(tables) == 6
assert sum(len(data['columns']) for data in tables.values()) == 101
assert sum(len(data['fk']) for data in tables.values()) == 5
overview_text, full_text = diagram(False), diagram(True)
(ROOT/'ER图_总览.mmd').write_text(overview_text, encoding='utf-8')
(ROOT/'ER图_完整字段.mmd').write_text(full_text, encoding='utf-8')
lines = ['# 问题管理 PostgreSQL ER图\n',
    '依据当前 ddl.sql（v0.2），2026-11-07。共6张表、101个字段、5条物理外键；总览省略部分字段，完整字段图保留全部列。\n',
    '[PNG总览](ER图_总览.png) · [SVG矢量图](ER图_总览.svg) · [总览Mermaid源文件](ER图_总览.mmd) · [完整字段Mermaid源文件](ER图_完整字段.mmd)\n',
    '## 总览\n', '```mermaid\n'+overview_text+'```\n',
    '## 图例与关联含义\n',
    '- `PK`为主键成员；`FK`为数据库已声明的物理外键。复合主键中的每个成员均标PK，不表示单列唯一。',
    '- `||`为恰好一个，`o{`为零到多；附件指向处理记录一端的`|o`表示零或一个。',
    '- 实线表示父键也是子表主键的一部分；虚线表示非标识关系。两种连线都可能是数据库物理外键，不能把虚线误读成外部引用。',
    '- 每个问题可以有多条处理记录、历史参与者、附件和可靠事件。附件必须归属一个问题，但可不关联具体处理记录（截图、临时上传等）。',
    '- 请求幂等表没有issue_id或问题外键，独立按租户、操作者、请求键去重；因此图中不连到问题表。\n',
    '|父表|子表及外键|基数|说明|\n|---|---|---|---|',
    '|im_issue|im_issue_action.issue_id|1 → 0..N|每条操作记录必须对应一个问题|',
    '|im_issue|im_issue_participant.issue_id|1 → 0..N|每条参与关系必须对应一个问题|',
    '|im_issue|im_issue_attachment.issue_id|1 → 0..N|每个附件必须对应一个问题|',
    '|im_issue_action|im_issue_attachment.action_id|0..1 ← 0..N|单个附件最多关联一条操作；单条操作可有多个附件|',
    '|im_issue|im_issue_outbox.issue_id|1 → 0..N|每个事件必须对应一个问题|\n',
    '图中的0..N依据数据库约束：外键不强制父记录至少有一条子记录。业务创建事务会同时写CREATE历史和参与者，这是应用规则。\n',
    '## 唯一约束\n','|表|约束|联合唯一字段|\n|---|---|---|']
for table, data in tables.items():
    for name, columns in data['unique']:
        lines.append(f'|{table}|{name}|{columns}|')
lines += ['\n可空唯一键成员遵循PostgreSQL默认语义：多条NULL不互相冲突。上述唯一约束均不能把某个成员单独视为唯一。\n',
    '## 外部逻辑引用与实现约束\n',
    '|字段范围|引用对象|数据库外键|\n|---|---|---|',
    '|tenant_id / org_id / project_id|租户、事业部、项目主数据|无，应用校验|',
    '|raiser_id / handler_id / user_id / operator_id / actor_id / uploaded_by等人员字段|统一用户服务|无，应用校验|',
    '|review_id / room_id|评审单、评审房间|无，应用校验|',
    '|baseline_id / report_id / annotation_id|数模基线、评审报告、批注|无，应用校验|',
    '|tc_uid|TC问题对象|无，集成服务维护|',
    '|object_key|对象存储中的文件|无，文件服务维护|\n',
    '以上均是逻辑引用，当前DDL未定义外部实体表，因此不绘制成已建物理表。',
    '子表tenant_id与主表一致性，以及附件action_id对应操作与附件issue_id归属同一问题，由应用事务校验；当前DDL的单列外键没有强制这两项跨字段一致性。',
    'outbox.issue_version是业务事件版本；它与处理记录的版本保持应用层一致，当前DDL没有声明指向action的复合外键。\n',
    '## 完整字段图\n','```mermaid\n'+full_text+'```\n',
    '完整图适合放大查看；精确约束表达式、索引、默认值见ddl.sql。重新生成Mermaid/SVG：`python generate_er.py`；Windows下重新生成PNG：`./render_er.ps1`。\n']
(ROOT/'ER图.md').write_text('\n'.join(lines), encoding='utf-8')
print('Generated overview/full Mermaid ER diagrams: 6 tables, 101 columns, 5 foreign keys.')

# 可直接查看/导出的总览图；与Mermaid读取相同字段和外键元数据。
ops = []
def rect(x,y,w,h,fill,stroke='#d8e1ec'):
    ops.append(dict(kind='rect',x=x,y=y,w=w,h=h,fill=fill,stroke=stroke))
def text(x,y,value,size=18,color='#26364b',weight='normal',family='Microsoft YaHei'):
    ops.append(dict(kind='text',x=x,y=y,value=value,size=size,color=color,weight=weight,family=family))
def line(points,color='#62768c',width=2,dash=False):
    ops.append(dict(kind='line',points=points,color=color,width=width,dash=dash))

rect(0,0,1800,1430,'#f5f8fc','#f5f8fc')
text(40,30,'问题管理 · PostgreSQL ER 图',38,weight='bold')
text(42,88,'6 张表  /  5 条物理外键  /  核心字段总览  /  依据 ddl.sql v0.2',21,'#62768c')
text(1500,49,'2026.11.07',19,'#62768c')

cards = {
 'im_issue': (620,180,560,'#243d66','业务当前快照；外部ID未声明数据库外键'),
 'im_issue_action': (40,180,510,'#3369a0','UK (issue_id, issue_version)；保存每轮处理'),
 'im_issue_participant': (1240,180,510,'#167d79','PK (issue_id, user_id)；转交后保留旧处理人'),
 'im_issue_attachment': (40,830,510,'#a86624','action_id 可空；截图/临时文件可无操作关联'),
 'im_issue_outbox': (1240,700,510,'#6a55a0','UK (issue_id, issue_version, destination)'),
 'im_issue_idempotency': (620,900,560,'#59697d','PK (tenant_id, actor_id, request_key)；无问题外键'),
}
for table,(x,y,w,color,footer) in cards.items():
    selected=overview[table]
    h=74+34*len(selected)+50
    rect(x,y,w,h,'#ffffff')
    rect(x,y,w,74,color,color)
    text(x+18,y+8,aliases[table],23,'#ffffff','bold')
    text(x+18,y+41,table,18,'#e8f0fa',family='Consolas')
    for i,col in enumerate(selected):
        yy=y+74+i*34
        if i%2==0:
            rect(x+1,yy,w-2,34,'#f4f7fb','#f4f7fb')
        dtype,nullable=tables[table]['columns'][col]
        keys='/'.join(k for k,v in [('PK',col in tables[table]['pk']),('FK',col in tables[table]['fk'])] if v)
        text(x+13,yy+7,keys,14,color,'bold',family='Consolas')
        text(x+88,yy+6,col+(' ?' if nullable else ''),17,family='Consolas')
        short_type=dtype.lower().replace('timestamptz(3)','timestamptz').replace('varchar','v')
        text(x+w-125,yy+7,short_type,15,'#62768c',family='Consolas')
    text(x+14,y+h-34,footer,14,'#62768c')

# 线端用文字明确基数，线形不额外编码，避免与外部逻辑引用混淆。
line([(620,340),(550,340)])
text(605,306,'1',16)
text(552,348,'0..N',16)
line([(1180,330),(1240,330)])
text(1187,298,'1',16)
text(1200,339,'0..N',16)
line([(1180,585),(1210,585),(1210,815),(1240,815)])
text(1187,554,'1',16)
text(1200,824,'0..N',16)
line([(620,580),(585,580),(585,988),(550,988)])
text(600,549,'1',16)
text(552,999,'0..N',16)
line([(280,542),(280,830)])
text(292,558,'0..1',17)
text(292,792,'0..N',17)
text(294,670,'action_id（可空）',17,'#62768c')

rect(40,1285,1710,106,'#eaf0f7','#d8e1ec')
text(60,1299,'图例：PK 主键成员   /   FK 已声明的物理外键   /   ? 可空字段   /   0..N 零到多',18)
text(60,1330,'请求幂等表独立存在；人员、租户、项目、房间、基线、报告、批注、TC及文件均为外部逻辑引用。',18)
text(60,1361,'完整字段、联合唯一约束及一致性校验责任见 ER图.md；图中只绘制当前DDL真实存在的表与外键。',17,'#62768c')

svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1430" viewBox="0 0 1800 1430">',
     '<title>问题管理 PostgreSQL ER图</title>',
     '<desc>六张表及五条实际外键；请求幂等表无关联外键，附件操作外键可空。</desc>']
for op in ops:
    if op['kind']=='rect':
        svg.append(f'<rect x="{op["x"]}" y="{op["y"]}" width="{op["w"]}" height="{op["h"]}" fill="{op["fill"]}" stroke="{op["stroke"]}"/>')
    elif op['kind']=='text':
        svg.append(f'<text x="{op["x"]}" y="{op["y"]+op["size"]}" font-family="{op["family"]},sans-serif" font-size="{op["size"]}" font-weight="{op["weight"]}" fill="{op["color"]}">{escape(op["value"])}</text>')
    else:
        points=' '.join(f'{x},{y}' for x,y in op['points'])
        svg.append(f'<polyline points="{points}" stroke="{op["color"]}" stroke-width="{op["width"]}" fill="none"/>')
svg.append('</svg>')
(ROOT/'ER图_总览.svg').write_text('\n'.join(svg),encoding='utf-8')
(ROOT/'er-assets').mkdir(exist_ok=True)
(ROOT/'er-assets'/'scene.json').write_text(json.dumps(ops,ensure_ascii=False),encoding='utf-8')
print('Generated standalone SVG overview and rendering scene.')
