# 问题管理后端评审包 v0.2

依据工作区《交流评审首页.html》，2026-11-07。优先阅读需规评审清单.md；本稿不是已签字需求，数据库已按用户要求确定为PostgreSQL；部署版本、框架和集团规范待确认。

|文件|用途|
|---|---|
|需规评审清单.md|会上可直接使用的问题、矛盾、建议与确认责任|
|后端详细设计.md|状态机、权限、表关系、事务、TC及附件、验收场景|
|ddl.sql|PostgreSQL（14+兼容语法）六张表的建表建议稿，不含DROP，不连接真实数据库|
|字段字典.md|从DDL提取的字段类型、可空性和注释，可辅助建模器录入|
|ER图.md|6张表、5条物理外键的总览/完整字段ER图、基数与外部引用说明|
|ER图_总览.png / ER图_总览.svg|可直接用于评审展示的总览图片|
|ER图_总览.mmd / ER图_完整字段.mmd|可编辑的Mermaid图源|
|yapi.json|YApi原生分类数组格式，15个接口的请求/响应Schema|
|接口文档.md|与JSON同源生成的接口说明、字段及Schema|
|generate_contract.py|修改接口的源文件，Python标准库可直接运行|
|validate_artifacts.py|JSON/Schema结构、SQL基础结构、接口路径和工件一致性静态检查|
|校验结果.txt|本次实际检查结果与未验证事项|

先在YApi测试项目中选择数据管理→导入→YApi JSON，选yapi.json；接口均标为undone。不同公司分支的菜单/导入器可能不同，尚未实际导入目标实例。没有在文件内写真实Token/域名/项目ID。测试时配置环境base URL和Authorization；项目基础路径不要再次添加/api/v1，避免路径重复。上传接口的multipart boundary由客户端生成。

原生结构依据YMFE/YApi官方[JSON导出控制器](https://github.com/YMFE/yapi/blob/master/exts/yapi-plugin-export-data/controller.js)及[接口模型](https://github.com/YMFE/yapi/blob/master/server/models/interface.js)，使用分类name/desc/list以及req_body_is_json_schema、res_body_is_json_schema等字段。这不是Swagger/OpenAPI文件。

SQL仅供空测试库验证：选定测试库后执行ddl.sql；未连接真实数据库。当前环境未发现psql/postgres/docker命令，静态检查不能代替PostgreSQL实际执行验证。DDL包含BEGIN/COMMIT，建议用 `psql -X -v ON_ERROR_STOP=1 -d <测试库> -f ddl.sql` 执行（将占位符替换为真实测试库名）。使用迁移框架时由框架管理事务，可移除脚本的BEGIN/COMMIT。不要在未确认建模器DDL管理方式前直接建表。

范围：核心10个接口覆盖查询、详情、编辑、回复/确认、附件、转交；另外5个是创建/提交/激活/删除/TC重试依赖与扩展。原型的批量、导入、模板、AI尚需确认并补接口。公共人员检索/房间/文件/权限服务接口不在当前目录，需联调时接入现有契约。

重新生成：在本目录执行 `python generate_contract.py`，然后执行 `python validate_artifacts.py`。字段字典由校验脚本从DDL重新提取。

ER图直接读取ddl.sql生成：执行 `python generate_er.py` 更新Markdown、Mermaid及SVG；Windows下再执行 `./render_er.ps1` 更新PNG。图中的PK、FK、可空性及关联基数对应当前数据库约束；外部系统引用和应用层校验责任在ER图.md说明。
