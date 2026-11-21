# Conferência manual de KPIs (fora do código)

Dados exportados por `etl/13_exportar_conferencia.py` e contas refeitas em planilha em 20/11/2026.

| KPI | Banco e painel | Planilha | Confere |
|---|---|---|---|
| % do valor com controle feminino (entre feminino e masculino) | 19,867% | 19,867% | sim |
| Sócios elegíveis em 2+ fornecedores | 1.596 de 46.219 | 1.596 de 46.219 | sim |

**Método.** KPI 1: soma do valor por classe com `SOMASE` e razão feminino ÷ (feminino + masculino) sobre 184.274 contratos. KPI 2: pares sócio × fornecedor ordenados por sócio, contagem sequencial por sócio e contagem dos que chegam a 2, sobre 48.365 pares. Os arquivos exportados ficam em `data/processed/conferencia/`, fora do Git.