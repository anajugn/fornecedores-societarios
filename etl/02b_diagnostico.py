"""Diagnóstico do contratos.parquet: datas, valores extremos."""
import duckdb
from config import INTERIM

P = (INTERIM / "contratos.parquet").as_posix()
con = duckdb.connect()


def show(titulo, sql):
    print(f"\n== {titulo} ==")
    for r in con.execute(sql).fetchall():
        print("  ", r)


show("contratos por ano de assinatura",
     f"SELECT year(data_assinatura) AS ano, count(*) FROM '{P}' GROUP BY 1 ORDER BY 1")
show("publicação mín/máx",
     f"SELECT min(data_publicacao), max(data_publicacao) FROM '{P}'")
show("valor > 0: acima de R$ 1 bi (qtd, soma)",
     f"""SELECT valor_global > 1000000000 AS acima_1bi, count(*), sum(valor_global)
         FROM '{P}' WHERE valor_global > 0 GROUP BY 1 ORDER BY 1""")
show("10 maiores valor_global (órgão, valor)",
     f"SELECT left(orgao_razao_social, 45), valor_global FROM '{P}' ORDER BY valor_global DESC LIMIT 10")