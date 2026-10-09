-- 小信助手智能体：创建数据库用户和数据库（以 postgres 超级用户执行）
-- 执行：
--   sudo -u postgres psql -v ON_ERROR_STOP=1 -v db_user=xiaoxin -v db_pass='强密码' -v db_name=xiaoxin < 00_create_db.sql
-- 可重复执行：用户已存在时只更新密码，数据库已存在时跳过

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_pass')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user') \gexec
SELECT format('ALTER ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_pass') \gexec

-- template0 + UTF8：不受 template1 编码影响，保证中文正常存储
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8'' TEMPLATE template0', :'db_name', :'db_user')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name') \gexec

-- 业务库只允许属主和超级用户连接
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'db_name') \gexec
SELECT format('GRANT ALL ON DATABASE %I TO %I', :'db_name', :'db_user') \gexec
