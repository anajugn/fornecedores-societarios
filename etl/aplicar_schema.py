"""Aplica um arquivo .sql no banco. Uso: python aplicar_schema.py [arquivo.sql]"""
import sys
import psycopg2
from config import DATABASE_URL, ROOT

if not DATABASE_URL:
    sys.exit("DATABASE_URL vazio: confira o .env na raiz do projeto")

arquivo = sys.argv[1] if len(sys.argv) > 1 else "schema.sql"
sql = (ROOT / "etl" / "sql" / arquivo).read_text(encoding="utf-8")

with psycopg2.connect(DATABASE_URL, connect_timeout=30) as con, con.cursor() as cur:
    cur.execute(sql)
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema = 'public' ORDER BY 1""")
    tabelas = [r[0] for r in cur.fetchall()]

print(f"{arquivo} aplicado. Tabelas no banco ({len(tabelas)}): {', '.join(tabelas)}")