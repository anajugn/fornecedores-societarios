# Dicionário de dados do banco (9 tabelas)

Definição em `etl/sql/schema.sql`; carga por `etl/07_carregar_aiven.py`.

## fato_contrato (190.806 linhas)
| Coluna | Tipo | Origem e regra |
|---|---|---|
| numero_controle_pncp | text, PK | PNCP; identificador do contrato |
| sk_orgao | integer, FK | `dim_orgao` pelo CNPJ do órgão |
| cnpj_raiz_fornecedor | char(8), FK | 8 primeiros dígitos do CNPJ do fornecedor (RN-01); nulo para PF, estrangeiro e raiz sem cadastro |
| sk_tempo | integer, FK | data de assinatura em `yyyymmdd` |
| sk_modalidade | integer, FK | `dim_modalidade`, chave `tipo_contrato_id * 100 + categoria_processo_id` |
| codigo_ibge | char(7) | município da unidade contratante (não do fornecedor) |
| valor_global | numeric(18,2) | PNCP; valor contratado (> 0 e ≤ R$ 1 bi, RN-02) |
| valor_parcela | numeric(18,2) | PNCP; nulo em 29,7% dos contratos |
| prazo_dias | integer | dias entre início e fim da vigência; nulo se o fim for anterior ao início |
| objeto_contrato | text | PNCP; truncado em 500 caracteres |
| sancionado_na_assinatura | boolean | RN-08, não implementada (sempre falso) |

## dim_fornecedor (28.235)
| Coluna | Tipo | Origem e regra |
|---|---|---|
| cnpj_raiz | char(8), PK | raiz do CNPJ |
| razao_social | text | Receita; "EMPRESARIO INDIVIDUAL (NOME OMITIDO)" para natureza 2135 |
| porte | text | código 01 Microempresa; 03 Empresa de pequeno porte; 05 Demais; outro: Não informado |
| natureza_juridica | text | "código - descrição" (domínio da Receita) |
| cnae_principal | char(7) | CNAE do estabelecimento (matriz primeiro) |
| codigo_ibge | char(7) | município do estabelecimento, traduzido do código da Receita; nulo em 20 fornecedores |
| uf | char(2) | UF do estabelecimento |
| classificacao_controle | text | feminino, masculino, misto_indeterminado ou sem_socio (RN-05) |
| n_socios_elegiveis | smallint | sócios elegíveis pela RN-03 |
| pct_indeterminados | numeric(5,2) | % de elegíveis com gênero indeterminado |

## dim_socio (48.952) e ponte_empresa_socio (51.393)
| Coluna | Tipo | Origem e regra |
|---|---|---|
| dim_socio.sk_socio | serial, PK | chave substituta |
| dim_socio.id_derivado | text, único | hash de 16 caracteres (sal + máscara do CPF + nome); nunca o CPF |
| dim_socio.tipo | char(2) | PF, PJ ou ES (identificador de sócio 2, 1 ou 3) |
| dim_socio.genero | char(1) | F, M ou I (RN-04, limiar de 90%); sempre I para PJ e ES |
| dim_socio.confianca | numeric(4,3) | maior frequência de gênero do primeiro nome, de 0 a 1 |
| dim_socio.faixa_etaria | smallint | código da faixa etária da Receita |
| ponte.cnpj_raiz, sk_socio | PK composta com `qualificacao` | vínculo empresa e sócio |
| ponte.qualificacao | text | descrição da qualificação do sócio |
| ponte.data_entrada | date | data de entrada na sociedade |
| ponte.elegivel | boolean | sócio conta para o controle (RN-03) |

## Dimensões menores
| Tabela | Colunas | Observação |
|---|---|---|
| dim_orgao (50) | sk_orgao, orgao_cnpj (14), razao_social, esfera_id, poder_id | os 50 maiores por valor |
| dim_municipio (5.570) | codigo_ibge (7), nome, uf, populacao, pct_negra, pct_branca | Censo 2022; `pct_negra` = preta + parda |
| dim_cnae (1.359) | cnae (7), descricao, pct_negra_setor, pct_mulher_setor | as duas últimas não são preenchidas |
| dim_modalidade (54) | sk_modalidade, id_origem, nome | "tipo de contrato \| categoria do processo" |
| dim_tempo (365) | sk_tempo (yyyymmdd), data, ano, mes, trimestre | calendário de 2025 |

## Arquivos intermediários e de saída
| Arquivo | Colunas | Gerado por |
|---|---|---|
| socios_classificados.parquet | cnpj_basico, id_derivado, tipo, genero, confianca, qualificacao_socio, qual_desc, data_entrada_sociedade, faixa_etaria, elegivel | `06` |
| empresas_classificadas.parquet | cnpj_basico, classificacao_controle, motivo, n_socios_total, n_socios_elegiveis, pct_indeterminados, tem_socio_pj, n_f, n_m, n_i | `06` |
| municipios_cor_raca.parquet | codigo_ibge, nome, uf, populacao, pct_negra, pct_branca, pct_preta, pct_parda, pct_amarela, pct_indigena | `08` |
| municipios_receita_ibge.parquet | cod_receita (4 dígitos), uf, codigo_ibge (7 dígitos) | `08` |

## Agregados materializados (`etl/sql/agregados.sql`)
| Visão | Conteúdo |
|---|---|
| mv_valor_por_classe | contratos, fornecedores, valor total e mediano por classe de controle |
| mv_genero_por_uf | o mesmo por UF do fornecedor e classe (só grupos com 5+ fornecedores) |
| mv_genero_por_faixa_racial | o mesmo por faixa de pretos e pardos e classe (só grupos com 5+ fornecedores) |
| mv_fornecedor_valor | valor por fornecedor (concentração), sem a classe |
| mv_socios_compartilhados | quantos sócios aparecem em 1, 2, 3, 4 ou 5+ fornecedores |