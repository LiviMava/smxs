"""有限的静态契约检查；不冒充PostgreSQL执行、完整JSON Schema验证或YApi实机导入。"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
data = json.loads((ROOT/'yapi.json').read_text(encoding='utf-8'))
assert isinstance(data, list) and len(data) == 2
seen = set()
schema_count = 0

def check_schema(schema):
    global schema_count
    schema_count += 1
    assert isinstance(schema, dict)
    if 'anyOf' in schema:
        assert len(schema['anyOf']) >= 2
        for sub in schema['anyOf']:
            check_schema(sub)
        return
    assert schema.get('type') in ['object','array','string','integer','boolean','null']
    if schema['type'] == 'object':
        props = schema['properties']
        assert set(schema.get('required',[])) <= set(props)
        assert len(schema.get('required',[])) == len(set(schema.get('required',[])))
        for prop in props.values():
            check_schema(prop)
    if schema['type'] == 'array':
        check_schema(schema['items'])
    if 'enum' in schema:
        assert schema['enum'] and len(set(schema['enum'])) == len(schema['enum'])

for cat in data:
    assert cat['name'] and isinstance(cat['list'], list)
    for api in cat['list']:
        key = api['method'],api['path']
        assert key not in seen, key
        seen.add(key)
        assert api['path'].startswith('/api/v1/')
        assert set(re.findall(r'\{(\w+)\}',api['path'])) == {p['name'] for p in api['req_params']}
        assert api['status'] == 'undone'
        assert any(h['name']=='Authorization' for h in api['req_headers'])
        if api['method'] != 'GET':
            assert any(h['name']=='Idempotency-Key' for h in api['req_headers'])
        if api['req_body_is_json_schema']:
            schema=json.loads(api['req_body_other'])
            check_schema(schema)
            if '{issueId}' in api['path']:
                assert 'version' in schema['required']
        check_schema(json.loads(api['res_body']))
assert len(seen)==15
assert [len(c['list']) for c in data]==[10,5]

# 生成稳定性：同源重新生成，不应改变已有工件。
before={n:(ROOT/n).read_bytes() for n in ['yapi.json','接口文档.md']}
subprocess.run([sys.executable,str(ROOT/'generate_contract.py')],check=True,capture_output=True)
assert all((ROOT/n).read_bytes()==v for n,v in before.items())

sql=(ROOT/'ddl.sql').read_text(encoding='utf-8')
assert not re.search(r'\b(DROP|TRUNCATE)\s+TABLE\b',sql,re.I)
assert not re.search(r'\b(DATETIME|TINYINT|ENGINE|CHARSET|UNIQUE KEY)\b', sql)
assert 'BEGIN;' in sql and 'COMMIT;' in sql
tables=re.findall(r'CREATE TABLE (\w+) \(\n(.*?)\n\);',sql,re.S)
assert len(tables)==6
names={name for name,_ in tables}
constraints=re.findall(r'CONSTRAINT (\w+)',sql)
assert len(constraints)==len(set(constraints))
comments={(table,col):text for table,col,text in re.findall(r"COMMENT ON COLUMN (\w+)\.(\w+) IS '((?:''|[^'])*)';",sql)}
dictionary=['# 问题管理字段字典（PostgreSQL DDL提取）\n',
    '数据库已确定PostgreSQL，语法按14+兼容设计，部署版本及字段长度待确认；草稿与提交的条件必填、角色可编辑范围以详设和接口契约为准。\n']
column_count=0
table_columns={}
for name,body in tables:
    columns={}
    for line in body.splitlines():
        m=re.match(r'\s{2}(\w+) (VARCHAR\(\d+\)|CHAR\(\d+\)|TIMESTAMPTZ\(3\)|TEXT|JSONB|BIGINT|BOOLEAN|UUID|INT)(.*)',line)
        if m:
            col,typ,tail=m.groups()
            assert col not in columns
            columns[col]=(typ,tail)
    assert 'tenant_id' in columns
    assert 'PRIMARY KEY' in body
    table_columns[name]=columns
    column_count+=len(columns)
    dictionary += [f'\n## {name}\n','|字段|数据库类型|可空|说明|\n|---|---|---|---|']
    for col,(typ,tail) in columns.items():
        comment=comments.get((name,col),'通用审计/技术字段，见详设')
        dictionary.append(f"|{col}|{typ}|{'否' if 'NOT NULL' in tail else '是'}|{comment}|")
for table,body in tables:
    for target,col in re.findall(r'REFERENCES (\w+)\((\w+)\)',body):
        assert target in names and col in table_columns[target]
    for col,target,target_col in re.findall(r'FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)',body):
        assert table_columns[table][col][0] == table_columns[target][target_col][0]
indexes=re.findall(r'CREATE INDEX (\w+) ON (\w+) \(([^)]+)\)',sql)
assert len({name for name,_,_ in indexes}) == len(indexes)
for name,table,cols in indexes:
    assert table in table_columns
    assert all(col.strip().split()[0] in table_columns[table] for col in cols.split(','))
for table,col in comments:
    assert table in table_columns and col in table_columns[table]
assert table_columns['im_issue']['id'][0] == 'UUID'
assert table_columns['im_issue_action']['adopted'][0] == 'BOOLEAN'
assert table_columns['im_issue_outbox']['payload'][0] == 'JSONB'
assert table_columns['im_issue']['created_at'][0] == 'TIMESTAMPTZ(3)'
(ROOT/'字段字典.md').write_text('\n'.join(dictionary)+'\n',encoding='utf-8')

report=f'''静态校验通过
日期：2026-11-07
YApi分类：2；接口：15（核心10、依赖/扩展5）
检查：JSON可解析、方法路径唯一、路径参数一致、鉴权/幂等头、更新版本必填。
Schema节点：{schema_count}；检查属性类型、required引用、枚举、嵌套结构。
DDL：PostgreSQL，6张表，{column_count}个字段，{len(indexes)}个普通/部分索引；检查主键存在、约束名唯一、外键目标及类型、索引字段、COMMENT引用、UUID/BOOLEAN/JSONB/TIMESTAMPTZ映射、无DROP/TRUNCATE及旧方言语法。
工件一致性：重新生成yapi.json及接口文档.md，字节完全相同。
字段字典：已从本次DDL生成。

未验证：PostgreSQL实例实际执行、完整SQL语法/约束行为、完整JSON Schema元模式验证、目标YApi实机导入、运行中的后端接口、TC/文件/权限联调。
当前未发现psql/postgres/initdb/pg_ctl/docker命令及pglast/psycopg库，未为此安装额外依赖。
这里的检查是工件结构检查，不是业务验收通过或可上线证明。
'''
(ROOT/'校验结果.txt').write_text(report,encoding='utf-8')
print(report)
