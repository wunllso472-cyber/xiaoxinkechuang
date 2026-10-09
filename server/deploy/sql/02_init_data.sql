-- 小信助手智能体：PostgreSQL 基础数据脚本（不含演示数据和知识库）
-- 由 python -m app.init_data --export-sql 生成于 2026-10-09 17:52，请勿手工修改
-- 执行：psql -h 127.0.0.1 -U xiaoxin -d xiaoxin -v ON_ERROR_STOP=1 -f 02_init_data.sql
-- 仅用于空库：sys_user 已有数据时脚本报错退出，不会写入任何数据
-- 知识库（信创运维知识库 + 示例文档、信创政策知识库）由服务首次启动时自动创建并导入

BEGIN;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM sys_user) THEN
    RAISE EXCEPTION '数据库中已有用户数据，基础数据脚本只能在空库上执行';
  END IF;
END $$;

-- alert_rule（9 条）
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (1, 'CPU使用率过高', 'cpu_usage', '>', '90', '中', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (2, '内存使用率过高', 'mem_usage', '>', '90', '中', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (3, '磁盘空间不足', 'disk_usage', '>', '90', '高', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (4, '违规双系统', 'dual_system', '=', '1', '高', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (5, '长期离线', 'offline_days', '>', '7', '低', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (6, '配件更换', 'hw_change', '=', '1', '中', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (7, 'U盘使用', 'usb', '=', '1', '低', FALSE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (8, '违规软件', 'blacklist_app', 'in', '迅雷,thunder,steam,qq游戏', '中', TRUE, '');
INSERT INTO alert_rule (id, name, metric, operator, threshold, level, enabled, description) VALUES (9, '非信创终端', 'non_xinchuang', '=', '1', '低', FALSE, '');
SELECT setval(pg_get_serial_sequence('alert_rule', 'id'), (SELECT max(id) FROM alert_rule));

-- chat_intent（2 条）
INSERT INTO chat_intent (id, name, keywords, description, slots, action, enabled) VALUES (1, '故障报修', '报修,坏了,故障,打不开,无法开机,蓝屏,黑屏', '收集报修信息后自动创建运维工单', '[{"name": "device", "label": "故障设备类型（电脑/打印机/网络等）", "required": true}, {"name": "problem", "label": "故障现象描述", "required": true}, {"name": "address", "label": "所在地点（楼层/房间）", "required": true}, {"name": "phone", "label": "联系电话", "required": true, "pattern": "(1[3-9]\\d{9})"}]', 'create_ticket', TRUE);
INSERT INTO chat_intent (id, name, keywords, description, slots, action, enabled) VALUES (2, '会议室预订', '订会议室,预订会议室', '', '[{"name": "time", "label": "时间", "required": true}, {"name": "people", "label": "人数", "required": true}, {"name": "preference", "label": "偏好(投影/视频)", "required": false}]', 'none', FALSE);
SELECT setval(pg_get_serial_sequence('chat_intent', 'id'), (SELECT max(id) FROM chat_intent));

-- client_config（8 条）
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('dual_system_check', '双系统监测进程', '0', 'startup', '客户端启动时执行');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('hardware_collect', '配件信息采集', '3600', 'interval', '间隔秒数');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('load_collect', '运行负载采集(心跳)', '300', 'interval', '间隔秒数');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('run_data_collect', '运行数据采集(应用/U盘/打印)', '1800', 'interval', '间隔秒数');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('message_poll', '消息拉取', '120', 'interval', '间隔秒数');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('version_check', '版本检查', '0', 'startup', '客户端启动时执行');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('idle_process_cpu', '闲置进程判定CPU阈值(%)', '0.5', 'manual', '进程优化使用');
INSERT INTO client_config (key, name, value, trigger, description) VALUES ('big_file_mb', '大文件阈值(MB)', '100', 'manual', '大文件检索使用');

-- cloud_server（2 条）
INSERT INTO cloud_server (id, name, ip, spec, location, remark) VALUES (1, '云桌面服务器-01', '10.10.1.11', '鲲鹏920 64核/256G', '机房A', '');
INSERT INTO cloud_server (id, name, ip, spec, location, remark) VALUES (2, '云桌面服务器-02', '10.10.1.12', '飞腾S2500 64核/256G', '机房A', '');
SELECT setval(pg_get_serial_sequence('cloud_server', 'id'), (SELECT max(id) FROM cloud_server));

-- contract_template（1 条）
INSERT INTO contract_template (id, name, category, industry, clauses, content, created_at) VALUES (1, '信创终端采购合同标准模板', '采购合同', '政企', '[{"name": "合同标的", "required": true, "keywords": ["标的", "采购内容", "货物清单", "产品清单"]}, {"name": "合同金额", "required": true, "keywords": ["合同金额", "合同价款", "总价"]}, {"name": "付款方式", "required": true, "keywords": ["付款", "支付"]}, {"name": "交付与验收", "required": true, "keywords": ["交付", "交货", "验收"]}, {"name": "质量保证", "required": true, "keywords": ["质保", "保修", "质量保证"]}, {"name": "违约责任", "required": true, "keywords": ["违约"]}, {"name": "保密条款", "required": false, "keywords": ["保密"]}, {"name": "知识产权", "required": false, "keywords": ["知识产权"]}, {"name": "不可抗力", "required": false, "keywords": ["不可抗力"]}, {"name": "争议解决", "required": true, "keywords": ["争议", "纠纷"]}, {"name": "合同生效", "required": true, "keywords": ["生效"]}]', '', now());
SELECT setval(pg_get_serial_sequence('contract_template', 'id'), (SELECT max(id) FROM contract_template));

-- dict_item（21 条）
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (1, 'cpu', 'Phytium', '飞腾', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (2, 'cpu', 'FT-2000', '飞腾FT-2000/4', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (3, 'cpu', 'D2000', '飞腾D2000', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (4, 'cpu', 'Kunpeng', '鲲鹏', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (5, 'cpu', 'HUAWEI Kunpeng 920', '鲲鹏920', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (6, 'cpu', 'Hygon', '海光', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (7, 'cpu', 'ZHAOXIN', '兆芯', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (8, 'cpu', 'KX-6000', '兆芯KX-6000', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (9, 'cpu', 'Loongson', '龙芯', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (10, 'cpu', 'Intel', 'Intel', '非信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (11, 'cpu', 'AMD', 'AMD', '非信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (12, 'os', 'Kylin', '银河麒麟', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (13, 'os', 'UOS', '统信UOS', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (14, 'os', 'UnionTech', '统信UOS', '信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (15, 'os', 'Ubuntu', 'Ubuntu', '非信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (16, 'os', 'Windows', 'Windows', '非信创', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (17, 'brand', 'LENOVO', '联想', '', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (18, 'brand', 'Huawei', '华为', '', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (19, 'brand', 'TsingHua Tongfang', '清华同方', '', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (20, 'brand', 'GreatWall', '长城', '', '');
INSERT INTO dict_item (id, dict_type, raw_value, std_value, extra, remark) VALUES (21, 'brand', 'Inspur', '浪潮', '', '');
SELECT setval(pg_get_serial_sequence('dict_item', 'id'), (SELECT max(id) FROM dict_item));

-- eval_set（1 条）
INSERT INTO eval_set (id, name, items, created_at) VALUES (1, '信创运维基础测试集', '[{"question": "银河麒麟系统如何查看系统版本？", "answer": "使用 cat /etc/os-release 或 nkvers 命令查看", "keywords": ["os-release", "nkvers"]}, {"question": "统信UOS下打印机无法打印一般如何排查？", "answer": "检查CUPS服务、驱动、连接与打印队列", "keywords": ["CUPS", "驱动", "队列"]}, {"question": "飞腾CPU属于什么架构？", "answer": "ARM架构（ARMv8）", "keywords": ["ARM"]}]', now());
SELECT setval(pg_get_serial_sequence('eval_set', 'id'), (SELECT max(id) FROM eval_set));

-- llm_model（5 条）
INSERT INTO llm_model (id, name, provider, base_url, api_key, model, temperature, top_p, max_tokens, timeout, priority, weight, scene, version, gray_percent, enabled, is_default, extra, health, last_check, created_at) VALUES (1, 'DeepSeek-Chat', 'deepseek', 'https://api.deepseek.com/v1', '', 'deepseek-chat', 0.7, 0.95, 2048, 60, 1, 1, '', 'v1', 100, TRUE, TRUE, NULL, '未知', NULL, now());
INSERT INTO llm_model (id, name, provider, base_url, api_key, model, temperature, top_p, max_tokens, timeout, priority, weight, scene, version, gray_percent, enabled, is_default, extra, health, last_check, created_at) VALUES (2, 'DeepSeek-Reasoner', 'deepseek', 'https://api.deepseek.com/v1', '', 'deepseek-reasoner', 0.6, 0.95, 4096, 120, 2, 1, '', 'v1', 100, FALSE, FALSE, NULL, '未知', NULL, now());
INSERT INTO llm_model (id, name, provider, base_url, api_key, model, temperature, top_p, max_tokens, timeout, priority, weight, scene, version, gray_percent, enabled, is_default, extra, health, last_check, created_at) VALUES (3, 'Qwen-Plus', 'qwen', 'https://dashscope.aliyuncs.com/compatible-mode/v1', '', 'qwen-plus', 0.7, 0.95, 2048, 60, 3, 1, '', 'v1', 100, FALSE, FALSE, NULL, '未知', NULL, now());
INSERT INTO llm_model (id, name, provider, base_url, api_key, model, temperature, top_p, max_tokens, timeout, priority, weight, scene, version, gray_percent, enabled, is_default, extra, health, last_check, created_at) VALUES (4, '星辰大模型(TeleChat)', 'telechat', 'http://127.0.0.1:8080/v1', '', 'telechat', 0.7, 0.95, 2048, 60, 4, 1, '', 'v1', 100, FALSE, FALSE, NULL, '未知', NULL, now());
INSERT INTO llm_model (id, name, provider, base_url, api_key, model, temperature, top_p, max_tokens, timeout, priority, weight, scene, version, gray_percent, enabled, is_default, extra, health, last_check, created_at) VALUES (5, '本地兜底(Mock)', 'mock', '', '', 'mock', 0.7, 0.95, 2048, 60, 99, 1, '', 'v1', 100, TRUE, FALSE, NULL, '未知', NULL, now());
SELECT setval(pg_get_serial_sequence('llm_model', 'id'), (SELECT max(id) FROM llm_model));

-- message_template（2 条）
INSERT INTO message_template (id, name, title, content, created_at) VALUES (1, '系统升级通知', '小信助手升级通知', '尊敬的用户：小信助手将于{时间}升级至新版本，届时请保持终端开机联网。', now());
INSERT INTO message_template (id, name, title, content, created_at) VALUES (2, '安全提醒', '终端安全提醒', '请勿在信创终端上安装未经授权的软件，禁止使用双系统。', now());
SELECT setval(pg_get_serial_sequence('message_template', 'id'), (SELECT max(id) FROM message_template));

-- review_rule（33 条）
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (1, 'R001', '合同名称完整', '要素完整性', 'element_required', '{"element": "合同名称"}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (2, 'R002', '甲方信息完整', '要素完整性', 'element_required', '{"element": "甲方"}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (3, 'R003', '乙方信息完整', '要素完整性', 'element_required', '{"element": "乙方"}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (4, 'R004', '合同金额明确', '要素完整性', 'element_required', '{"element": "合同金额(小写)"}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (5, 'R005', '大写金额存在', '要素完整性', 'element_required', '{"element": "合同金额(大写)"}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (6, 'R006', '大小写金额一致', '金额审查', 'amount_consistent', '{}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (7, 'R007', '履行期限明确', '要素完整性', 'element_required', '{"element": "履行期限"}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (8, 'R008', '付款方式明确', '要素完整性', 'element_required', '{"element": "付款方式"}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (9, 'R009', '违约责任条款', '条款完整性', 'keyword_required', '{"keywords": ["违约"]}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (10, 'R010', '争议解决条款', '条款完整性', 'keyword_required', '{"keywords": ["争议", "纠纷", "仲裁", "诉讼"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (11, 'R011', '质保条款', '条款完整性', 'keyword_required', '{"keywords": ["质保", "保修", "质量保证"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (12, 'R012', '验收条款', '条款完整性', 'keyword_required', '{"keywords": ["验收"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (13, 'R013', '保密条款', '条款完整性', 'keyword_required', '{"keywords": ["保密"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (14, 'R014', '知识产权条款', '条款完整性', 'keyword_required', '{"keywords": ["知识产权"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (15, 'R015', '不可抗力条款', '条款完整性', 'keyword_required', '{"keywords": ["不可抗力"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (16, 'R016', '合同生效条款', '条款完整性', 'keyword_required', '{"keywords": ["生效"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (17, 'R017', '签字盖章完整性', '签章审查', 'keyword_required', '{"keywords": ["盖章", "签章", "公章", "合同专用章"]}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (18, 'R018', '法定代表人/授权代表签字', '签章审查', 'keyword_required', '{"keywords": ["法定代表人", "授权代表", "委托代理人"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (19, 'R019', '签订日期', '签章审查', 'regex_required', '{"pattern": "\\d{4}\\s*年\\s*\\d{1,2}\\s*月|\\d{4}-\\d{1,2}-\\d{1,2}", "message": "未找到签订日期"}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (20, 'R020', '终端单价阈值检查', '金额审查', 'amount_max', '{"pattern": "(?:终端|计算机|台式机|笔记本)[^\\n]{0,30}?单价[^\\n\\d]{0,10}([\\d,]+(?:\\.\\d+)?)\\s*元", "max": 12000}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (21, 'R021', '单项单价阈值检查', '金额审查', 'amount_max', '{"pattern": "单价[^\\n\\d]{0,10}([\\d,]+(?:\\.\\d+)?)\\s*元", "max": 500000}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (22, 'R022', '信创产品合规-禁用非信创CPU', '信创合规', 'keyword_forbidden', '{"keywords": ["Intel", "英特尔", "AMD 锐龙", "i5-", "i7-"]}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (23, 'R023', '信创产品合规-禁用非国产操作系统', '信创合规', 'keyword_forbidden', '{"keywords": ["Windows 10", "Windows 11", "Win10", "Win11"]}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (24, 'R024', '信创产品合规-国产化声明', '信创合规', 'keyword_required', '{"keywords": ["信创", "国产", "麒麟", "统信", "飞腾", "鲲鹏", "海光", "兆芯", "龙芯"]}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (25, 'R025', '禁止无限连带责任', '风险条款', 'keyword_forbidden', '{"keywords": ["无限连带", "无限责任"]}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (26, 'R026', '禁止单方任意变更', '风险条款', 'regex_forbidden', '{"pattern": "乙方有权[^\\n。]{0,20}(单方|随时)[^\\n。]{0,10}(变更|调整|解除)"}', '高', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (27, 'R027', '违约金比例上限', '风险条款', 'regex_forbidden', '{"pattern": "违约金[^\\n。]{0,20}(?:[3-9]\\d|100)\\s*%"}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (28, 'R028', '预付款比例检查', '付款审查', 'regex_forbidden', '{"pattern": "预付[^\\n。]{0,15}(?:[5-9]\\d|100)\\s*%"}', '中', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (29, 'R029', '发票条款', '付款审查', 'keyword_required', '{"keywords": ["发票"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (30, 'R030', '交付地点明确', '条款完整性', 'keyword_required', '{"keywords": ["交货地点", "交付地点", "实施地点", "送货地点"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (31, 'R031', '售后服务响应时间', '条款完整性', 'regex_required', '{"pattern": "\\d+\\s*(?:小时|h|分钟)内?[^\\n。]{0,10}(?:响应|到场|上门)", "message": "未约定售后响应时间"}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (32, 'R032', '禁止模糊表述', '文本规范', 'keyword_forbidden', '{"keywords": ["等等", "原则上", "视情况而定", "另行商定"]}', '低', TRUE, 1, 0, 0, '');
INSERT INTO review_rule (id, code, name, category, rule_type, params, level, enabled, version, hit_count, false_positive, description) VALUES (33, 'R033', '合同编号存在', '要素完整性', 'element_required', '{"element": "合同编号"}', '低', TRUE, 1, 0, 0, '');
SELECT setval(pg_get_serial_sequence('review_rule', 'id'), (SELECT max(id) FROM review_rule));

-- sys_setting（6 条）
INSERT INTO sys_setting (key, value, description) VALUES ('route_strategy', '"priority"', '');
INSERT INTO sys_setting (key, value, description) VALUES ('chat', '{"session_timeout_minutes": 60, "context_window_rounds": 6, "context_strategy": "window"}', '');
INSERT INTO sys_setting (key, value, description) VALUES ('planned_terminals', '{"_all": 0}', '');
INSERT INTO sys_setting (key, value, description) VALUES ('indicator_thresholds', '{"接入率": 90, "替代完成率": 80, "活跃率": 70, "双轨率": 20, "违规双系统数": 0}', '');
INSERT INTO sys_setting (key, value, description) VALUES ('client_key', '""', '');
INSERT INTO sys_setting (key, value, description) VALUES ('open_api_keys', '[]', '');

-- sys_user（6 条）
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (1, 'admin', '9d4e470545811e32$362dbe8db6d0ac2b5119584d57e0d20c28163736a03655e62df7338413b5991c', '系统管理员', 'admin', '市保障中心', '', '', TRUE, now());
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (2, 'kefu', 'a475227b6453d03f$621ee571d0edbcd4abed22eba10a6af64f1d0e18dca59e5c8f9aa182c6cedaf3', '客服小王', 'cs', '市保障中心', '', '', TRUE, now());
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (3, 'yunwei1', '2d69c68635772c55$c336028ad8f5a65165bd199547cfae57169045c5623899549bdbfe824543eede', '运维张工', 'ops', '市保障中心', '', '', TRUE, now());
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (4, 'yunwei2', 'ef876977ab6ec87f$002b3c0e8f2a5e101c39155739260f6c61b3e424218749a4ad2e36958ed4ae65', '运维李工', 'ops', '市保障中心', '', '', TRUE, now());
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (5, 'changshang', 'e3fd739a0580378b$3c758b0c7953ba4ab50d4b4ed7c546f354970c9ee4d9eba974f7947fedfd0a20', '厂商赵工', 'ops', '市保障中心', '某信创厂商', '', TRUE, now());
INSERT INTO sys_user (id, username, password_hash, real_name, role, station, company, phone, enabled, created_at) VALUES (6, 'xqyunwei', '673ef0e3cce77195$492196f6ddc8aa85ea479ba55542f0b6eaca0ddb23f979e3b3ad7eefe0773b1c', '区县运维陈工', 'ops', '西湖区保障站', '', '', TRUE, now());
SELECT setval(pg_get_serial_sequence('sys_user', 'id'), (SELECT max(id) FROM sys_user));

-- tool（7 条）
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (1, 'ocr', 'OCR文字识别', 'builtin', 'OCR文字识别', 'builtin', '', 'POST', 'none', '', '{"path": "图片路径"}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (2, 'image_analyze', '图片场景/图表分析', 'builtin', '图片场景/图表分析', 'builtin', '', 'POST', 'none', '', '{"path": "图片路径"}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (3, 'calculator', '计算器', 'builtin', '计算器', 'builtin', '', 'POST', 'none', '', '{"expression": "算式"}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (4, 'datetime', '当前时间', 'builtin', '当前时间', 'builtin', '', 'POST', 'none', '', '{}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (5, 'kb_search', '知识库检索', 'builtin', '知识库检索', 'builtin', '', 'POST', 'none', '', '{"kb_id": "知识库ID", "query": "问题", "top_k": 3}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (6, 'doc_parse', '文档解析', 'builtin', '文档解析', 'builtin', '', 'POST', 'none', '', '{"path": "文件路径"}', 30, TRUE, '小信助手', now());
INSERT INTO tool (id, code, name, kind, description, protocol, endpoint, method, auth_type, auth_value, params_schema, timeout, enabled, provider, created_at) VALUES (7, 'summary', '文本摘要(大模型)', 'builtin', '文本摘要(大模型)', 'builtin', '', 'POST', 'none', '', '{"text": "文本"}', 30, TRUE, '小信助手', now());
SELECT setval(pg_get_serial_sequence('tool', 'id'), (SELECT max(id) FROM tool));

COMMIT;
