"""Monta docs/inventario_receita.xlsx a partir dos CSVs do inventário.
A aba Achados reproduz a saída de 00_inventario_receita.py de 20/11/2026."""
import pandas as pd
from config import INTERIM, ROOT

tam = pd.read_csv(INTERIM / "inventario_tamanhos.csv")
tam["gb"] = (tam.bytes / 1e9).round(3)
resumo = (tam.groupby("grupo").agg(arquivos=("arquivo", "count"), gb=("gb", "sum"))
          .round(2).reset_index())
resumo.loc[len(resumo)] = ["TOTAL", resumo.arquivos.sum(), round(resumo.gb.sum(), 2)]


def nulos(grupo):
    df = pd.read_csv(INTERIM / f"inventario_nulos_{grupo}.csv")
    return df.rename(columns={df.columns[0]: "coluna"})


achados = [
    ("Sócios", "Amostra", "200.000 primeiras linhas de Socios0.zip (sequencial, não aleatória)"),
    ("Sócios", "Pessoa física / jurídica / estrangeiro", "97,40% / 2,58% / 0,02%"),
    ("Sócios", "Linhas duplicadas", "18 (0,009%)"),
    ("Sócios", "Máscaras de CPF distintas (PF)", "166.980"),
    ("Sócios", "Pares máscara+nome distintos (PF)", "192.299 (usar só a máscara fundiria ~13,2%)"),
    ("Sócios", "representante_legal sem representante", "valor ***000000** e qualificação 00, não é nulo"),
    ("Estabelecimentos", "Amostra", "200.000 primeiras linhas de Estabelecimentos0.zip (sequencial)"),
    ("Estabelecimentos", "Matriz / filial", "97,63% / 2,37%"),
    ("Estabelecimentos", "Situação ativa / baixada / inapta / suspensa / nula",
     "50,11% / 44,25% / 5,12% / 0,33% / 0,20%"),
    ("Estabelecimentos", "E-mail preenchido", "99,14% (coluna descartada, LGPD)"),
    ("Estabelecimentos", "Tamanho do CNAE / município", "7 caracteres / 4 caracteres em 100% (município da Receita, não IBGE)"),
    ("Estabelecimentos", "Linhas duplicadas", "0"),
]

(ROOT / "docs").mkdir(exist_ok=True)
saida = ROOT / "docs" / "inventario_receita.xlsx"
with pd.ExcelWriter(saida) as w:
    resumo.to_excel(w, sheet_name="Volume", index=False)
    tam.to_excel(w, sheet_name="Arquivos", index=False)
    nulos("Socios").to_excel(w, sheet_name="Nulos_Socios", index=False)
    nulos("Estabelecimentos").to_excel(w, sheet_name="Nulos_Estab", index=False)
    pd.DataFrame(achados, columns=["base", "medida", "valor"]).to_excel(w, sheet_name="Achados", index=False)
print("gerado:", saida)