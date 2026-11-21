"""Valores idênticos entre fornecedores diferentes do mesmo órgão (possível valor da ata replicado)."""
import pandas as pd

from config import INTERIM

c = pd.read_parquet(INTERIM / "contratos_recorte.parquet")
c["v"] = c["valor_global"].astype(float)
c = c[c["cnpj_raiz_fornecedor"].notna()]
tot = c["v"].sum()
g = (c[c["v"] >= 1e7].groupby(["orgao_razao_social", "v"])
       .agg(contratos=("v", "size"), fornecedores=("cnpj_raiz_fornecedor", "nunique"))
       .reset_index())
g["valor_somado"] = g["v"] * g["contratos"]
rep = g[g["fornecedores"] >= 3].sort_values("valor_somado", ascending=False)
print(f"grupos (órgão e valor >= R$ 10 mi) com 3+ fornecedores diferentes: {len(rep)}")
print(f"valor somado: R$ {rep.valor_somado.sum() / 1e9:,.1f} bi ({100 * rep.valor_somado.sum() / tot:.1f}% do valor)")
print(rep.head(15).to_string(index=False))

if len(rep):
    t = rep.iloc[0]
    x = c[(c["orgao_razao_social"] == t["orgao_razao_social"]) & (c["v"] == t["v"])]
    print(f"\nmaior grupo: {t['orgao_razao_social']}, R$ {t['v']:,.2f}, {int(t['contratos'])} contratos")
    print(x[["numero_controle_pncp", "cnpj_raiz_fornecedor", "objeto_contrato"]]
          .assign(objeto_contrato=lambda d: d["objeto_contrato"].str[:90]).head(6).to_string(index=False))