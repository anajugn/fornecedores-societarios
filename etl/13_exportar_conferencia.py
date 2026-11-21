"""Exporta os dados brutos para conferir 2 KPIs do painel em planilha (fora do código).
Saída em data/processed/conferencia/ (fora do Git: tem classe de controle por empresa).

Uso:  python 13_exportar_conferencia.py
"""
import sys

from config import DATABASE_URL, PROCESSED, ROOT

sys.path.insert(0, str(ROOT / "app"))
import dados  # noqa: E402


def main():
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")
    d, ponte = dados.banco(DATABASE_URL)
    pasta = PROCESSED / "conferencia"
    pasta.mkdir(parents=True, exist_ok=True)

    k1 = d[["numero_controle", "cnpj_raiz", "classe", "valor"]]
    k1.to_csv(pasta / "kpi1_valor_por_classe.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")

    p = (ponte[ponte["cnpj_raiz"].isin(set(d["cnpj_raiz"]))].drop_duplicates()
         .sort_values(["sk_socio", "cnpj_raiz"]))
    p.to_csv(pasta / "kpi2_socios_fornecedores.csv", sep=";", index=False, encoding="utf-8-sig")

    fem = d.loc[d["classe"] == "feminino", "valor"].sum()
    mas = d.loc[d["classe"] == "masculino", "valor"].sum()
    por = p.groupby("sk_socio").size()
    print(f"gravado em {pasta}")
    print(f"kpi1: {len(k1):,} linhas. Valor esperado na planilha: {100 * fem / (fem + mas):.3f}% "
          "do valor das empresas de controle definido com controle feminino")
    print(f"kpi2: {len(p):,} linhas. Esperado: {len(por):,} sócios, dos quais {int((por >= 2).sum()):,} "
          "em 2 ou mais fornecedores")


if __name__ == "__main__":
    main()