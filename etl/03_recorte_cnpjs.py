"""RN-02, filtro de valor, top N órgãos e lista de raízes de CNPJ. Imprime o funil."""
import csv

import duckdb

from config import DATA_FIM, DATA_INI, INTERIM, N_ORGAOS, VALOR_MAX

P = lambda n: (INTERIM / n).as_posix()
con = duckdb.connect()
q = lambda s: con.execute(s).fetchone()[0]

con.execute(f"CREATE VIEW bruto AS SELECT * FROM '{P('contratos.parquet')}'")

etapas = [
    ("contratos tratados (deduplicados)", "true"),
    ("sem contrato de receita (receita = false)", "NOT receita"),
    ("valor_global > 0", "valor_global > 0"),
    (f"valor_global <= R$ {VALOR_MAX:,}", f"valor_global <= {VALOR_MAX}"),
    (f"assinados de {DATA_INI} a {DATA_FIM}",
     f"data_assinatura BETWEEN DATE '{DATA_INI}' AND DATE '{DATA_FIM}'"),
]
cond, funil = [], []
for nome, c in etapas:
    cond.append(c)
    funil.append((nome, q(f"SELECT count(*) FROM bruto WHERE {' AND '.join(cond)}")))

con.execute(f"CREATE TABLE elegiveis AS SELECT * FROM bruto WHERE {' AND '.join(cond)}")
con.execute(f"""
CREATE TABLE orgaos AS
SELECT orgao_cnpj, any_value(orgao_razao_social) AS orgao,
       count(*) AS contratos, sum(valor_global) AS valor
FROM elegiveis GROUP BY 1 ORDER BY valor DESC LIMIT {N_ORGAOS}""")
con.execute("CREATE TABLE recorte AS SELECT * FROM elegiveis WHERE orgao_cnpj IN (SELECT orgao_cnpj FROM orgaos)")

funil.append((f"top {N_ORGAOS} órgãos por valor", q("SELECT count(*) FROM recorte")))
funil.append(("  desses, fornecedor PJ com raiz de CNPJ",
              q("SELECT count(*) FROM recorte WHERE cnpj_raiz_fornecedor IS NOT NULL")))
funil.append(("  desses, fornecedor PF", q("SELECT count(*) FROM recorte WHERE tipo_pessoa = 'PF'")))
funil.append(("  desses, fornecedor PE", q("SELECT count(*) FROM recorte WHERE tipo_pessoa = 'PE'")))
funil.append(("raízes de CNPJ distintas (lista para o filtro da Receita)",
              q("SELECT count(DISTINCT cnpj_raiz_fornecedor) FROM recorte")))

con.execute(f"COPY orgaos  TO '{P('orgaos_recorte.csv')}' (HEADER)")
con.execute(f"COPY recorte TO '{P('contratos_recorte.parquet')}' (FORMAT PARQUET)")
con.execute(f"""COPY (SELECT DISTINCT cnpj_raiz_fornecedor AS cnpj_raiz FROM recorte
                WHERE cnpj_raiz_fornecedor IS NOT NULL ORDER BY 1)
                TO '{P('cnpjs_raiz.csv')}' (HEADER)""")

with open(INTERIM / "funil_recorte.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["etapa", "quantidade"])
    w.writerows(funil)

print("--- funil do recorte ---")
for nome, n in funil:
    print(f"{nome:<62} {n:>10,}")

total = q("SELECT sum(valor_global) FROM elegiveis")
top = q("SELECT sum(valor_global) FROM recorte")
print(f"\nvalor elegível (R$)      : {total:,.2f}")
print(f"valor dos top {N_ORGAOS} órgãos (R$): {top:,.2f}  ({top / total:.1%} do elegível)")
print("\n10 maiores órgãos por valor:")
for org, c, v in con.execute("SELECT left(orgao, 50), contratos, valor FROM orgaos LIMIT 10").fetchall():
    print(f"  {org:<50} {c:>8,} contratos  R$ {v:,.2f}")