"""A UF do contrato (fato_contrato.codigo_ibge) é a do órgão ou a do fornecedor?  Só leitura.
Uso:  python 14_checar_uf_orgao.py
"""
import sys

import pandas as pd
import psycopg2

from config import DATABASE_URL

SQL = """
SELECT o.razao_social AS orgao, mo.uf AS uf_contrato, f.uf AS uf_fornecedor, count(*) AS n
FROM fato_contrato c
JOIN dim_orgao o        ON o.sk_orgao = c.sk_orgao
JOIN dim_fornecedor f   ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
JOIN dim_municipio mo   ON mo.codigo_ibge = c.codigo_ibge
GROUP BY 1, 2, 3
"""


def main():
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")
    con = psycopg2.connect(DATABASE_URL, connect_timeout=30)
    cur = con.cursor()
    cur.execute("SELECT count(*) FILTER (WHERE codigo_ibge IS NULL), count(*) FROM fato_contrato")
    nulos, total = cur.fetchone()
    cur.execute(SQL)
    df = pd.DataFrame(cur.fetchall(), columns=["orgao", "uf_contrato", "uf_fornecedor", "n"])
    con.close()

    print(f"contratos sem codigo_ibge: {nulos:,} de {total:,}")
    igual = df.loc[df["uf_contrato"] == df["uf_fornecedor"], "n"].sum() / df["n"].sum()
    print(f"contratos em que a UF do contrato é igual à UF do fornecedor: {100 * igual:.1f}%")

    por = df.groupby(["orgao", "uf_contrato"])["n"].sum().reset_index()
    topo = por.sort_values("n", ascending=False).groupby("orgao").head(1).set_index("orgao")
    topo["total"] = por.groupby("orgao")["n"].sum()
    topo["parcela"] = (100 * topo["n"] / topo["total"]).round(1)
    topo = topo.rename(columns={"uf_contrato": "uf_principal"})[["uf_principal", "parcela", "total"]]
    print("\n10 maiores órgãos (UF principal e % dos contratos nela):")
    print(topo.sort_values("total", ascending=False).head(10).to_string())
    espalhados = topo[topo["parcela"] < 90].sort_values("total", ascending=False)
    print(f"\nórgãos com menos de 90% dos contratos numa UF só: {len(espalhados)} de {len(topo)}")
    print(espalhados.head(10).to_string())


if __name__ == "__main__":
    main()