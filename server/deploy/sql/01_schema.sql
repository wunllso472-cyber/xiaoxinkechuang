-- 小信助手智能体：PostgreSQL 建表脚本（39 张表）
-- 由 python -m app.init_data --export-sql 生成于 2026-10-09 17:52，请勿手工修改
-- 执行：psql -h 127.0.0.1 -U xiaoxin -d xiaoxin -v ON_ERROR_STOP=1 -f 01_schema.sql
-- 可重复执行：已存在的表和索引自动跳过

BEGIN;

CREATE TABLE IF NOT EXISTS alert (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	rule_id INTEGER, 
	rule_name VARCHAR(128), 
	level VARCHAR(8), 
	content TEXT, 
	status VARCHAR(16), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_alert_created_at ON alert (created_at);
CREATE INDEX IF NOT EXISTS ix_alert_device_id ON alert (device_id);

CREATE TABLE IF NOT EXISTS alert_rule (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	metric VARCHAR(32), 
	operator VARCHAR(8), 
	threshold VARCHAR(256), 
	level VARCHAR(8), 
	enabled BOOLEAN, 
	description VARCHAR(256), 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS chat_intent (
	id SERIAL NOT NULL, 
	name VARCHAR(64), 
	keywords VARCHAR(256), 
	description VARCHAR(256), 
	slots JSON, 
	action VARCHAR(32), 
	enabled BOOLEAN, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS chat_message (
	id SERIAL NOT NULL, 
	session_id VARCHAR(64), 
	role VARCHAR(16), 
	content TEXT, 
	model_name VARCHAR(128), 
	refs JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_chat_message_session_id ON chat_message (session_id);

CREATE TABLE IF NOT EXISTS chat_session (
	id VARCHAR(64) NOT NULL, 
	"user" VARCHAR(64), 
	device_id VARCHAR(64), 
	title VARCHAR(256), 
	mode VARCHAR(16), 
	model_id INTEGER, 
	kb_id INTEGER, 
	intent VARCHAR(64), 
	slots JSON, 
	summary TEXT, 
	expired BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	last_active TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS client_config (
	key VARCHAR(64) NOT NULL, 
	name VARCHAR(128), 
	value VARCHAR(256), 
	trigger VARCHAR(16), 
	description VARCHAR(256), 
	PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS client_version (
	id SERIAL NOT NULL, 
	version VARCHAR(32), 
	platform VARCHAR(16), 
	arch VARCHAR(16), 
	file_path VARCHAR(512), 
	changelog TEXT, 
	force_update BOOLEAN, 
	status VARCHAR(16), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS cloud_server (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	ip VARCHAR(64), 
	spec VARCHAR(256), 
	location VARCHAR(128), 
	remark VARCHAR(256), 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS contract (
	id SERIAL NOT NULL, 
	filename VARCHAR(256), 
	file_path VARCHAR(512), 
	file_type VARCHAR(16), 
	uploader VARCHAR(64), 
	text TEXT, 
	structure JSON, 
	elements JSON, 
	diff JSON, 
	review JSON, 
	risk_level VARCHAR(8), 
	status VARCHAR(16), 
	template_id INTEGER, 
	duration_ms INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS contract_template (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	category VARCHAR(64), 
	industry VARCHAR(64), 
	clauses JSON, 
	content TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS dict_item (
	id SERIAL NOT NULL, 
	dict_type VARCHAR(32), 
	raw_value VARCHAR(256), 
	std_value VARCHAR(256), 
	extra VARCHAR(256), 
	remark VARCHAR(256), 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS eval_run (
	id SERIAL NOT NULL, 
	eval_set_id INTEGER, 
	model_id INTEGER, 
	model_name VARCHAR(128), 
	params JSON, 
	accuracy FLOAT, 
	professional FLOAT, 
	avg_latency FLOAT, 
	results JSON, 
	status VARCHAR(16), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS eval_set (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	items JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ft_dataset (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	kind VARCHAR(16), 
	file_path VARCHAR(512), 
	total INTEGER, 
	valid INTEGER, 
	categories JSON, 
	processed_path VARCHAR(512), 
	status VARCHAR(16), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ft_job (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	dataset_id INTEGER, 
	base_model VARCHAR(128), 
	method VARCHAR(16), 
	params JSON, 
	status VARCHAR(16), 
	progress INTEGER, 
	metrics JSON, 
	log TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS kb (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	description VARCHAR(512), 
	owner VARCHAR(64), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS kb_chunk (
	id SERIAL NOT NULL, 
	kb_id INTEGER, 
	doc_id INTEGER, 
	seq INTEGER, 
	content TEXT, 
	vector JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_kb_chunk_doc_id ON kb_chunk (doc_id);
CREATE INDEX IF NOT EXISTS ix_kb_chunk_kb_id ON kb_chunk (kb_id);

CREATE TABLE IF NOT EXISTS kb_doc (
	id SERIAL NOT NULL, 
	kb_id INTEGER, 
	filename VARCHAR(256), 
	file_path VARCHAR(512), 
	file_type VARCHAR(16), 
	size INTEGER, 
	md5 VARCHAR(64), 
	version INTEGER, 
	parent_id INTEGER, 
	is_latest BOOLEAN, 
	tags VARCHAR(256), 
	tag_checked BOOLEAN, 
	status VARCHAR(16), 
	progress INTEGER, 
	chunk_count INTEGER, 
	filtered_count INTEGER, 
	retry INTEGER, 
	error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_kb_doc_kb_id ON kb_doc (kb_id);
CREATE INDEX IF NOT EXISTS ix_kb_doc_md5 ON kb_doc (md5);

CREATE TABLE IF NOT EXISTS kb_import_log (
	id SERIAL NOT NULL, 
	doc_id INTEGER, 
	level VARCHAR(8), 
	message TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_kb_import_log_doc_id ON kb_import_log (doc_id);

CREATE TABLE IF NOT EXISTS kb_rag_log (
	id SERIAL NOT NULL, 
	query TEXT, 
	kb_id INTEGER, 
	mode VARCHAR(16), 
	hit_count INTEGER, 
	top_score FLOAT, 
	retrieve_ms INTEGER, 
	generate_ms INTEGER, 
	feedback INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_kb_rag_log_created_at ON kb_rag_log (created_at);

CREATE TABLE IF NOT EXISTS llm_call_log (
	id SERIAL NOT NULL, 
	model_id INTEGER, 
	model_name VARCHAR(128), 
	scene VARCHAR(32), 
	latency_ms INTEGER, 
	success BOOLEAN, 
	error TEXT, 
	prompt_tokens INTEGER, 
	completion_tokens INTEGER, 
	fallback BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_llm_call_log_created_at ON llm_call_log (created_at);
CREATE INDEX IF NOT EXISTS ix_llm_call_log_model_id ON llm_call_log (model_id);

CREATE TABLE IF NOT EXISTS llm_model (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	provider VARCHAR(32), 
	base_url VARCHAR(512), 
	api_key VARCHAR(512), 
	model VARCHAR(128), 
	temperature FLOAT, 
	top_p FLOAT, 
	max_tokens INTEGER, 
	timeout INTEGER, 
	priority INTEGER, 
	weight INTEGER, 
	scene VARCHAR(128), 
	version VARCHAR(32), 
	gray_percent INTEGER, 
	enabled BOOLEAN, 
	is_default BOOLEAN, 
	extra JSON, 
	health VARCHAR(16), 
	last_check TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS message (
	id SERIAL NOT NULL, 
	title VARCHAR(256), 
	content TEXT, 
	scope_type VARCHAR(16), 
	scope_value VARCHAR(512), 
	send_type VARCHAR(16), 
	send_time TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR(16), 
	target_count INTEGER, 
	read_count INTEGER, 
	creator VARCHAR(64), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	sent_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS message_receipt (
	id SERIAL NOT NULL, 
	message_id INTEGER, 
	device_id VARCHAR(64), 
	delivered_at TIMESTAMP WITHOUT TIME ZONE, 
	read_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_message_receipt_device_id ON message_receipt (device_id);
CREATE INDEX IF NOT EXISTS ix_message_receipt_message_id ON message_receipt (message_id);

CREATE TABLE IF NOT EXISTS message_template (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	title VARCHAR(256), 
	content TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ops_case (
	id SERIAL NOT NULL, 
	title VARCHAR(256), 
	category VARCHAR(64), 
	question TEXT, 
	answer TEXT, 
	status VARCHAR(16), 
	quality BOOLEAN, 
	source_ticket_id INTEGER, 
	reporter VARCHAR(64), 
	station VARCHAR(64), 
	audit_comment VARCHAR(256), 
	view_count INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS ops_ticket (
	id SERIAL NOT NULL, 
	ticket_no VARCHAR(32), 
	title VARCHAR(256), 
	description TEXT, 
	category VARCHAR(64), 
	reporter VARCHAR(64), 
	reporter_phone VARCHAR(32), 
	dept VARCHAR(128), 
	address VARCHAR(256), 
	device_info VARCHAR(256), 
	source VARCHAR(16), 
	status VARCHAR(16), 
	station VARCHAR(64), 
	cs_id INTEGER, 
	assignee_id INTEGER, 
	assignee_name VARCHAR(64), 
	deadline TIMESTAMP WITHOUT TIME ZONE, 
	suspend_reason TEXT, 
	suspend_days INTEGER, 
	solution TEXT, 
	feedback TEXT, 
	rating INTEGER, 
	rating_comment VARCHAR(256), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	finished_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (ticket_no)
);
CREATE INDEX IF NOT EXISTS ix_ops_ticket_assignee_id ON ops_ticket (assignee_id);
CREATE INDEX IF NOT EXISTS ix_ops_ticket_status ON ops_ticket (status);

CREATE TABLE IF NOT EXISTS ops_ticket_log (
	id SERIAL NOT NULL, 
	ticket_id INTEGER, 
	action VARCHAR(32), 
	operator VARCHAR(64), 
	content TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_ops_ticket_log_ticket_id ON ops_ticket_log (ticket_id);

CREATE TABLE IF NOT EXISTS review_rule (
	id SERIAL NOT NULL, 
	code VARCHAR(32), 
	name VARCHAR(128), 
	category VARCHAR(32), 
	rule_type VARCHAR(32), 
	params JSON, 
	level VARCHAR(8), 
	enabled BOOLEAN, 
	version INTEGER, 
	hit_count INTEGER, 
	false_positive INTEGER, 
	description VARCHAR(256), 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS software (
	id SERIAL NOT NULL, 
	name VARCHAR(128), 
	version VARCHAR(32), 
	category VARCHAR(64), 
	platform VARCHAR(16), 
	description TEXT, 
	file_path VARCHAR(512), 
	size INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS sys_setting (
	key VARCHAR(64) NOT NULL, 
	value JSON, 
	description VARCHAR(256), 
	PRIMARY KEY (key)
);

CREATE TABLE IF NOT EXISTS sys_user (
	id SERIAL NOT NULL, 
	username VARCHAR(64), 
	password_hash VARCHAR(256), 
	real_name VARCHAR(64), 
	role VARCHAR(16), 
	station VARCHAR(64), 
	company VARCHAR(64), 
	phone VARCHAR(32), 
	enabled BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_sys_user_username ON sys_user (username);

CREATE TABLE IF NOT EXISTS terminal (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	hostname VARCHAR(128), 
	user_name VARCHAR(64), 
	dept VARCHAR(128), 
	ip VARCHAR(64), 
	mac VARCHAR(64), 
	os_name VARCHAR(128), 
	os_version VARCHAR(128), 
	arch VARCHAR(32), 
	cpu_model VARCHAR(256), 
	cpu_vendor VARCHAR(64), 
	cpu_cores INTEGER, 
	mem_total FLOAT, 
	disk_total FLOAT, 
	disk_model VARCHAR(256), 
	brand VARCHAR(128), 
	model VARCHAR(128), 
	serial VARCHAR(128), 
	is_xinchuang BOOLEAN, 
	dual_system BOOLEAN, 
	is_cloud_desktop BOOLEAN, 
	cloud_server VARCHAR(128), 
	client_version VARCHAR(32), 
	cpu_usage FLOAT, 
	mem_usage FLOAT, 
	disk_usage FLOAT, 
	status VARCHAR(16), 
	boot_time TIMESTAMP WITHOUT TIME ZONE, 
	hw_snapshot JSON, 
	first_seen TIMESTAMP WITHOUT TIME ZONE, 
	last_seen TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_terminal_device_id ON terminal (device_id);

CREATE TABLE IF NOT EXISTS terminal_active_day (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	day DATE, 
	online_minutes INTEGER, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_terminal_active_day_day ON terminal_active_day (day);
CREATE INDEX IF NOT EXISTS ix_terminal_active_day_device_id ON terminal_active_day (device_id);

CREATE TABLE IF NOT EXISTS terminal_hw_change (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	component VARCHAR(64), 
	old_value TEXT, 
	new_value TEXT, 
	confirmed BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_terminal_hw_change_device_id ON terminal_hw_change (device_id);

CREATE TABLE IF NOT EXISTS terminal_load_record (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	cpu FLOAT, 
	mem FLOAT, 
	disk FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_terminal_load_record_created_at ON terminal_load_record (created_at);
CREATE INDEX IF NOT EXISTS ix_terminal_load_record_device_id ON terminal_load_record (device_id);

CREATE TABLE IF NOT EXISTS terminal_run_record (
	id SERIAL NOT NULL, 
	device_id VARCHAR(64), 
	kind VARCHAR(32), 
	content JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_terminal_run_record_created_at ON terminal_run_record (created_at);
CREATE INDEX IF NOT EXISTS ix_terminal_run_record_device_id ON terminal_run_record (device_id);
CREATE INDEX IF NOT EXISTS ix_terminal_run_record_kind ON terminal_run_record (kind);

CREATE TABLE IF NOT EXISTS tool (
	id SERIAL NOT NULL, 
	code VARCHAR(64), 
	name VARCHAR(128), 
	kind VARCHAR(16), 
	description VARCHAR(512), 
	protocol VARCHAR(16), 
	endpoint VARCHAR(512), 
	method VARCHAR(8), 
	auth_type VARCHAR(16), 
	auth_value VARCHAR(512), 
	params_schema JSON, 
	timeout INTEGER, 
	enabled BOOLEAN, 
	provider VARCHAR(128), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE IF NOT EXISTS tool_call_log (
	id SERIAL NOT NULL, 
	tool_code VARCHAR(64), 
	success BOOLEAN, 
	latency_ms INTEGER, 
	error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_tool_call_log_created_at ON tool_call_log (created_at);
CREATE INDEX IF NOT EXISTS ix_tool_call_log_tool_code ON tool_call_log (tool_code);

COMMIT;
