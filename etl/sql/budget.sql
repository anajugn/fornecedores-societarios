SELECT relname AS tabela,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_total_relation_size(relid) AS bytes
FROM pg_catalog.pg_statio_user_tables
ORDER BY bytes DESC;

SELECT pg_size_pretty(pg_database_size(current_database())) AS banco_total;