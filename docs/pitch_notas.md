# Notas do pitch

## Mensagem central
Quem são as pessoas por trás dos CNPJs que recebem dinheiro público? Em 184 mil contratos de 2025 (50 órgãos), as empresas de controle feminino são cerca de 30% dos contratos, e o contrato mediano delas vale 0,67 do das masculinas. O valor total é dominado por poucos contratos e por valores repetidos, então medimos em cinco cenários e usamos mediana e contagem como medida principal.

## Roteiro (10 min)
| Tempo | Bloco | Quem | Conteúdo |
|---|---|---|---|
| 0:00 | Problema | T4 | pergunta central, Q1, Q2, Q3, recorte (2025, 50 órgãos, 52,5% do valor) |
| 1:00 | Dados e 5 V's | T2 | Receita 25,5 GB descompactados, 171,8 milhões de linhas; PNCP 2 milhões de contratos; 4 tipos de dado |
| 2:30 | Infraestrutura | T1 | Terraform + Aiven free (1 GB), diagrama, reprovisionamento em clone limpo, limites do plano gratuito |
| 4:00 | Processamento | T2 | streaming sem gravar o bruto; 25,5 GB → 4,1 MB (6.181×); Pandas × PostgreSQL com honestidade; relacional × não relacional |
| 5:15 | LGPD | T4 | hash com sal, sem nome nem CPF no banco, proxy territorial no lugar de cor/raça, TSE rejeitado, mínimo de 5 |
| 6:15 | Demonstração | T3 | painel ao vivo (roteiro abaixo) |
| 8:15 | Achados e limites | T3 | razão das medianas 0,67 estável; sem gradiente racial; valor replicado em 1/3 do total |
| 9:30 | Fechamento | T1 | o que o projeto prova, o que não prova, próximos passos |

## Roteiro da demonstração (2 min)
1. Aba Gênero: 19,9% do valor com controle feminino. Marcar "Excluir valores possivelmente replicados" e mostrar que vira 17,4% (e que a razão das medianas não muda).
2. Trocar a métrica para "valor mediano": a razão feminino ÷ masculino fica perto de 0,67.
3. Clicar na barra "Feminino": o painel inteiro filtra (filtro cruzado).
4. Aba Interseccional: ler o aviso (proxy territorial) e mostrar que não há gradiente.
5. Aba Concentração: Gini e 1% maior; sócios em 2+ fornecedores (1.596).
6. Drill-down: UF, órgão, maiores contratos. Mostrar que a classe de controle não aparece por empresa.

## Antes de apresentar (no dia)
- Religar o serviço do Aiven pelo menos 30 minutos antes (plano gratuito desliga por inatividade) e confirmar com `python etl/checar_aiven.py`.
- Abrir o painel 10 minutos antes e esperar carregar (a primeira consulta demora, depois fica em cache por 1 hora). Se vier erro, Reboot app.
- Rodar `python -m pytest tests -q` (80 testes) e deixar o terminal pronto.
- Não rodar `terraform apply` ao vivo: o plano gratuito permite um serviço só, e com o serviço no ar o segundo apply falha com 403. Mostrar `terraform plan` ou `terraform state list` (serviço Running) e citar as evidências de `docs/` do clone limpo.
- Dados do painel: confirmar que o aviso amarelo de dados fictícios NÃO aparece.

## Perguntas prováveis da banca
| Pergunta | Resposta curta |
|---|---|
| Por que inferir gênero pelo primeiro nome? | Não há campo de gênero nos dados públicos. Usamos o Censo (IBGE) com limiar de 90%: abaixo disso, "indeterminado" (4,3% dos sócios). O piloto mostrou o efeito do limiar (80% a 99%). Uso só agregado. |
| Por que o Censo 2010 e não o 2022? | A v3 do Censo 2022 não consta da documentação pública da API. A diferença para o piloto da 1ª Unidade foi de 1,9 ponto e está declarada. |
| Por que não usar cor/raça individual? | Dado sensível. O cruzamento com o TSE ligaria nome a cor autodeclarada e foi rejeitado. Usamos o percentual do município (Censo 2022) como proxy e avisamos que é falácia ecológica ler isso como cor do sócio. |
| Como garantem que não há dado pessoal no banco? | Sem coluna de nome ou CPF; sócio só por hash com sal (fora do Git); testes automáticos falham se aparecer nome ou formato de CPF. |
| Por que o Pandas foi mais rápido que o PostgreSQL? | Em 190 mil linhas o Pandas em memória não paga rede (164 ms de latência até o Aiven). O banco vence em integridade (190.806 linhas passaram por chaves e CHECK), compartilhamento e agregados pré-calculados. Não é benchmark: uma máquina, 5 repetições. |
| Por que relacional e não NoSQL? | Há uma relação N:N (empresa e sócio, 51 mil vínculos) e perguntas de junção e agregação. O bruto fica em arquivos (esquema flexível). Usamos os dois. |
| Por que só 50 órgãos, se o banco usa 102 MB de 1 GB? | Os 50 maiores têm 52,5% do valor. O número é parâmetro do script, mas ampliar refaz Receita, classificação e carga, e todos os números mudam. Ficou como próximo passo. |
| O CIMINAS não distorce tudo? | Distorce o valor (41%). Por isso há cenários sem ele, sem contratos acima de R$ 100 mi e sem valores repetidos. A razão das medianas fica em 0,67 ou 0,68 nos cinco. |
| Os valores repetidos são erro? | Em 49 de 53 grupos o objeto é idêntico (31,9% do valor): indício forte de teto de credenciamento repetido. Não excluímos nada; marcamos e oferecemos o cenário. |
| O resultado prova assimetria de acesso? | Não. Os 31,5% não têm baseline externo (faltaria a base inteira da Receita). O achado firme é o tamanho do contrato. |
| E o proxy racial, mostra discriminação? | Não. Não há gradiente (razão 0,34, 0,63, 0,60 e 1,19) e as faixas se confundem com regiões. É descrição, sem causa. |
| Por que a regra de administradores? | Segue o roteiro: administradores contam como controle. Testamos a versão estrita: controle definido 58,5% contra 63,9%, femininas 32,7% contra 31,5%. |
| Como o sistema escala? | O filtro é streaming por arquivo (4,3 min para 171 milhões de linhas) e a saída é Parquet. O limite está no plano gratuito do banco (1 GB, 20 conexões). |
| Como vocês testam? | 80 testes: regras recalculadas sobre os dados, unitários e do painel, mais conferência independente por SQL e conferência manual em planilha de 2 KPIs. |
| O que fariam com mais tempo? | RN-08 (CEIS e CNEP), proxy setorial (RAIS ou CAGED), baseline com a base inteira da Receita, ingestão incremental, painel lendo os agregados. |
| A Receita veio de um espelho? | Sim, o portal oficial estava fora do ar. Os arquivos são os da Receita e a fonte está declarada. |