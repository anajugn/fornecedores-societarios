# Teste comparativo: Pandas x PostgreSQL (5 repetições, mediana)

Latência do banco (`SELECT 1`): 164,5 ms. Leitura dos 3 Parquet: 0.32 s. Criação dos agregados: 5.7 s (2.21 MB).

| Consulta | Resultados conferem | Pandas (lê Parquet + calcula) | Pandas (já em memória) | PostgreSQL (junções nas tabelas) | PostgreSQL (agregado materializado) |
|---|---|---|---|---|---|
| A. valor por classe de controle (junção de 2 tabelas) | sim | 340,9 ms | 181,9 ms | 473,1 ms | 163,8 ms |
| B. sócios em 2+ fornecedores (junção N:N pela ponte) | sim | 710,2 ms | 406,9 ms | 370,2 ms | 164,1 ms |
| C. 10 maiores fornecedores (agregação) | sim | 312,8 ms | 164,1 ms | 811,9 ms | 261,5 ms |
