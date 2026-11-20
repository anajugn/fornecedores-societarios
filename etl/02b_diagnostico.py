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
R = (INTERIM / "contratos_recorte.parquet").as_posix()
show("recorte: 15 maiores valor_global (órgão, valor)",
     f"SELECT left(orgao_razao_social, 40), valor_global FROM '{R}' ORDER BY valor_global DESC LIMIT 15")
show("recorte: contratos acima de cada limiar (limiar, qtd, % do valor do recorte)",
     f"""SELECT t, count(*) FILTER (WHERE valor_global > t) AS contratos,
                round(100 * sum(valor_global) FILTER (WHERE valor_global > t) / sum(valor_global), 1) AS pct_valor
         FROM '{R}', (VALUES (10000000), (50000000), (100000000), (500000000)) AS l(t)
         GROUP BY t ORDER BY t""")
show("valor_parcela e valor_acumulado nulos ou zero (% dos contratos)",
     f"""SELECT round(100.0 * count(*) FILTER (WHERE coalesce(valor_parcela, 0) = 0) / count(*), 1),
                round(100.0 * count(*) FILTER (WHERE coalesce(valor_acumulado, 0) = 0) / count(*), 1)
         FROM '{P}'""")