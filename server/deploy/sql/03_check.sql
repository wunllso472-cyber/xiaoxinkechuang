-- 小信助手智能体：初始化结果检查（以业务用户执行，只读）
-- 执行：psql -h 127.0.0.1 -U xiaoxin -d xiaoxin -f 03_check.sql

\echo '== 1. 数据库版本与编码（版本 >= 10，编码 UTF8）'
SELECT version();
SELECT pg_encoding_to_char(encoding) AS 编码 FROM pg_database WHERE datname = current_database();

\echo '== 2. 表数量（应为 39）'
SELECT count(*) AS 表数量 FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

\echo '== 3. 基础数据条数（括号内为初始值）'
SELECT '用户 sys_user (6)' AS 数据, count(*) AS 条数 FROM sys_user
UNION ALL SELECT '系统设置 sys_setting (6)', count(*) FROM sys_setting
UNION ALL SELECT '大模型 llm_model (5)', count(*) FROM llm_model
UNION ALL SELECT '客户端配置 client_config (8)', count(*) FROM client_config
UNION ALL SELECT '预警规则 alert_rule (9)', count(*) FROM alert_rule
UNION ALL SELECT '数据字典 dict_item (21)', count(*) FROM dict_item
UNION ALL SELECT '意图 chat_intent (2)', count(*) FROM chat_intent
UNION ALL SELECT '合同审查规则 review_rule (33)', count(*) FROM review_rule
UNION ALL SELECT '合同模板 contract_template (1)', count(*) FROM contract_template
UNION ALL SELECT '工具 tool (7)', count(*) FROM tool
UNION ALL SELECT '消息模板 message_template (2)', count(*) FROM message_template
UNION ALL SELECT '云桌面服务器 cloud_server (2)', count(*) FROM cloud_server
UNION ALL SELECT '评估测试集 eval_set (1)', count(*) FROM eval_set
UNION ALL SELECT '知识库 kb (2，服务首次启动后)', count(*) FROM kb
UNION ALL SELECT '演示终端 terminal (生产应为 0)', count(*) FROM terminal;

\echo '== 4. 用户'
SELECT id, username, real_name, role, station, enabled FROM sys_user ORDER BY id;

\echo '== 5. 大模型'
SELECT id, name, provider, model, enabled, is_default, priority, (api_key <> '') AS 已填key FROM llm_model ORDER BY priority;

\echo '== 6. 知识库示例文档（服务首次启动后：状态完成，分片数 > 0）'
SELECT k.name AS 知识库, d.filename, d.status, count(c.id) AS 分片数
  FROM kb k LEFT JOIN kb_doc d ON d.kb_id = k.id LEFT JOIN kb_chunk c ON c.doc_id = d.id
 GROUP BY k.name, d.filename, d.status ORDER BY k.name;

\echo '== 7. 自增序列（last_value 应不小于对应表的最大 id）'
SELECT 'sys_user' AS 表, (SELECT max(id) FROM sys_user) AS 最大id, last_value FROM sys_user_id_seq
UNION ALL SELECT 'llm_model', (SELECT max(id) FROM llm_model), last_value FROM llm_model_id_seq
UNION ALL SELECT 'review_rule', (SELECT max(id) FROM review_rule), last_value FROM review_rule_id_seq;
