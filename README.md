# Contratações Públicas e Fornecedores Societários

Big Data e Analytics, projeto prático, tema 9.
Grupo: Afonso de Menezes Alves Neto, Ana Júlia Gusmão do Nascimento, Iago César Lacerda Santos, Pedro Lucas Felix Aragão.

Pergunta central: **quem são as pessoas por trás dos CNPJs que recebem dinheiro público, e há assimetria de gênero e de cor/raça nesse controle?**

> **Estado em 20/11/2026 (remover na entrega).** Concluído: Terraform e banco no Aiven (reprovisionado em clone limpo), schema, inventário da Receita, tratamento dos contratos, funil do recorte, filtro da Receita, piloto de gênero e classificação de sócios e empresas, mapa de colunas e parecer de LGPD. Em andamento: coleta do PNCP de 2025. Todo número marcado como *parcial* vem de uma coleta de 01/01 a 30/04/2025 (120 dias) e será refeito com o ano fechado. `[PREENCHER]` depende de medição; `[CONFIRMAR]` depende de decisão do grupo.

## 1. Problema, perguntas analíticas e recorte

- **Q1** Assimetria de gênero: participação de empresas de controle feminino no valor contratado e no número de contratos.
- **Q3** Concentração societária: quantos sócios (pessoas, não CNPJs) concentram o valor contratado; sócios em comum; vínculo com sancionados (CEIS/CNEP).
- **Q2** Camada interseccional: gênero do controle cruzado com composição de cor/raça por proxy setorial e territorial.

**Coleta:** contratos publicados no PNCP de 01/01/2025 a 31/12/2025, pela API de consulta (por data de publicação), um arquivo por dia.

**Recorte analítico (RN-02):** contratos de despesa, com valor global maior que zero e até R$ 1 bilhão, **assinados em 2025**, dos 50 órgãos de maior valor contratado.

**Justificativa do recorte por órgão:** (1) a Receita filtrada e o `fato_contrato` precisam caber no PostgreSQL gratuito (1 GB); (2) nos dados parciais, os 50 órgãos concentram 58,2% do valor elegível com 7,3% dos contratos. O valor de N é o ponto de partida e pode subir se o tamanho medido no banco (`etl/sql/budget.sql`) permitir. `[PREENCHER: N final e tamanho medido]`

**Viés de seleção declarado:** órgãos grandes (federais, estados, consórcios de saúde) pesam mais que municípios pequenos, então comparações entre UFs não representam o país.

**Funil do recorte (parcial, publicados de 01/01 a 30/04/2025):**

| Etapa | Contratos |
|---|---|
| Registros brutos | 580.776 |
| Após deduplicação por `numeroControlePNCP` | 572.866 |
| Sem contratos de receita | 567.691 |
| Valor global maior que zero | 563.632 |
| Valor global até R$ 1 bilhão | 563.547 |
| Assinados em 2025 | 460.951 |
| Top 50 órgãos por valor | 33.672 |
| Fornecedor PJ com CNPJ de 14 dígitos | 30.903 |
| Fornecedor PF | 2.574 |
| Fornecedor estrangeiro (PE) | 195 |
| Raízes de CNPJ distintas (lista para o filtro da Receita) | 10.366 |

Valor elegível: R$ 160,1 bilhões. Valor dos 50 órgãos: R$ 93,2 bilhões (58,2%).

## 2. LGPD e dados abertos

Texto completo em [`docs/lgpd.md`](docs/lgpd.md). Resumo:
- Contratos e quadro societário são dados públicos (Lei 12.527/2011 e Decreto 8.777/2016).
- Nome de sócio é dado pessoal mesmo sendo público: o CPF nunca é armazenado e o nome não é carregado no banco; o banco guarda um identificador derivado (hash com sal secreto). O painel só publica agregados com no mínimo 5 sócios ou empresas por recorte (RN-09).
- Cor/raça é dado sensível (LGPD, art. 5º, II): não é inferida por pessoa, só por proxy ecológico (setor e município) atribuído ao contexto da empresa (RN-06).
- **Caminho rejeitado:** cruzar nome de sócio com bases de cor/raça autodeclarada (por exemplo candidaturas do TSE) seria reidentificação de dado sensível.
- Minimização na ingestão: e-mail, telefones, endereço, CEP, dados do representante legal e o campo `usuarioNome` do PNCP (quem enviou o contrato, que pode ser pessoa física) não são carregados. A razão social de empresário individual, que costuma ser o nome da pessoa, é substituída por um texto genérico no banco.

## 3. Os 5 V's (números reais)

| V | Número medido | Decisão do pipeline |
|---|---|---|
| Volume | Receita: 7,76 GB compactado em 37 ZIP (Estabelecimentos 5,38; Empresas 1,38; Sócios 0,69; Simples 0,31; domínio menos de 0,01). Filtro da Receita: 7,45 GB lidos em streaming (Sócios, Empresas e Estabelecimentos), 171,8 milhões de linhas, 130.727 mantidas (0,076%), em cerca de 4 minutos. PNCP: 580.776 registros nos primeiros 120 dias; JSON bruto de 1,08 GB em 137 dias (média de 7,9 MB por dia); Parquet de contratos de 101,8 MB (120 dias). Estimativa linear para o ano: cerca de 1,8 milhão de contratos, 2,9 GB de JSON bruto e 310 MB de Parquet | Receita lida em streaming (nada vai para o disco); Parquet na camada analítica; o Postgres recebe só o recorte |
| Velocidade | PNCP publica contratos todos os dias, com atraso: 98,3% dos contratos assinados fora de 2025 são de 2024, publicados em 2025; Receita atualiza mensalmente. `[PREENCHER: workflow do GitHub Actions]` | coleta incremental, retomável, um arquivo por dia; ingestão em lote agendada |
| Variedade | CSV (Receita), JSON aninhado (PNCP) e texto livre (`objetoContrato`) | DuckDB para o JSON, Parquet para a camada analítica |
| Veracidade | 1,4% de duplicatas no PNCP; 0,74% de valores menores ou iguais a zero; 87 contratos acima de R$ 1 bi concentrando 96,6% do valor somado (até R$ 1,1 trilhão: erro de digitação); 133 datas de assinatura impossíveis (ano 2026 ou 8406, posteriores à publicação); `valor_parcela` nulo ou zero em 32,1% dos contratos e `valor_acumulado` em 77,3%; 18 duplicatas em 200 mil linhas de sócios; 166.980 máscaras de CPF contra 192.299 pares máscara+nome (usar só a máscara fundiria cerca de 13,2% das identidades); nomes de sócio sem classificação de gênero: 5,6% no piloto de 1.000 e 4,4% nos 17.403 sócios PF do recorte parcial; cobertura da Receita sobre as raízes do recorte: Empresas e Estabelecimentos 100%, Sócios 88,5% | deduplicação por chave natural; filtros da RN-02; só `valor_global` como métrica; identificador do sócio = máscara + nome; categoria "indeterminado" em vez de forçar classe |
| Valor | `[PREENCHER: achados da Fase 2]` | KPIs do painel |

As amostras de sócios e estabelecimentos da Receita no inventário são sequenciais (primeiras 200 mil linhas de um arquivo), não aleatórias.

## 4. Tipos de dado, colunas e fontes complementares

### 4.1 Os três tipos, com exemplo real

**Estruturado.** CSV da Receita (`;`, sem cabeçalho, latin-1). Sócios, com nome reduzido à inicial e máscara do CPF ocultada:

```
cnpj_basico  identificador_socio  nome_socio  cnpj_cpf_socio  qualificacao_socio  data_entrada_sociedade  faixa_etaria
12340763     2                    Z***        ***######**     22                  20100805                6
12340798     2                    D***        ***######**     22                  20170809                9
```

**Semi-estruturado.** JSON do PNCP, com objetos aninhados. Um contrato real, com 14 dos 41 campos:

```json
{
  "numeroControlePNCP": "04564530000113-2-000059/2024",
  "orgaoEntidade": {"cnpj": "04564530000113", "razaoSocial": "RONDONIA SECRETARIA DE ESTADO DA EDUCACAO", "poderId": "E", "esferaId": "E"},
  "unidadeOrgao": {"ufSigla": "RO", "municipioNome": "Porto Velho", "codigoIbge": "1100205"},
  "tipoContrato": {"id": 8, "nome": "Outros"},
  "categoriaProcesso": {"id": 2, "nome": "Compras"},
  "tipoPessoa": "PJ",
  "niFornecedor": "15086536000149",
  "nomeRazaoSocialFornecedor": "Chez Editora LTDA",
  "receita": false,
  "valorGlobal": 2058500.0,
  "valorParcela": 0.0,
  "dataAssinatura": "2024-12-31",
  "dataPublicacaoPncp": "2025-01-02T03:45:00",
  "objetoContrato": "SOLUÇÃO EDUCACIONAIS TECNOLÓGICAS - LEI 14.133/2021"
}
```

Este contrato foi assinado em 2024 e publicado em 2025: fica fora do recorte pela RN-02. Também mostra `valorParcela` igual a zero com uma parcela. Medido nos dados parciais, `valor_parcela` é nulo ou zero em 32,1% dos contratos e `valor_acumulado` em 77,3%; o painel usa só `valor_global`.

**Não estruturado.** O campo `objetoContrato`: texto livre em português, sem vocabulário controlado, em caixa alta, com referência legal embutida (exemplo acima).

### 4.2 Colunas usadas e descartadas

Mapa completo em [`docs/mapa_colunas.md`](docs/mapa_colunas.md). Em resumo: dos 41 campos do contrato do PNCP, 21 são lidos; da Receita ficam as colunas das regras RN-01 a RN-09, e saem endereço, telefone, e-mail, dados do representante legal e país do sócio.

### 4.3 Fontes complementares

| Uso | Fonte | Estado |
|---|---|---|
| Gênero (RN-04) | API de nomes do IBGE, `api/v2/censos/nomes/{nome}?sexo=F` e `sexo=M` (Censo 2010, documentada) | Testada em 20/11/2026 (status 200): devolve a frequência de nascimentos por década e por sexo; somamos as décadas, com duas chamadas por lote de nomes. A v3 (Censo 2022) existe, mas não consta na documentação pública das APIs do IBGE. O documento da 1ª Unidade usou o Censo 2022; a troca para a v2 se justifica pela documentação e porque sócios de empresa são, em geral, adultos nascidos antes de 2010 |
| Proxy territorial de cor/raça (RN-06) | SIDRA, Censo 2022, tabela 9605, "População residente, por cor ou raça, nos Censos Demográficos" (2010 a 2022), classificação 86 (Cor ou raça) | Confirmada em 20/11/2026: tem nível município (N6). Usar o período 2022 |
| Proxy setorial de cor/raça (RN-06) | RAIS ou Novo CAGED (PDET), por CNAE | escopo condicional; sem CNPJ do empregador, o cruzamento é por CNAE e município, nunca por empresa |

### 4.4 Piloto de gênero (RN-04)

Amostra: 1.000 sócios pessoa física sorteados (semente 42) entre as 200 mil primeiras linhas de `Socios0.zip` (amostra sequencial, não aleatória), com 538 primeiros nomes distintos. Fonte: API de nomes do IBGE v2 (Censo 2010). Limiar de 90%.

| Classificação | Sócios | % |
|---|---|---|
| Feminino | 372 | 37,2% |
| Masculino | 572 | 57,2% |
| Indeterminado: ambíguo (categoria dominante abaixo de 90%) | 21 | 2,1% |
| Indeterminado: nome ausente da base | 35 | 3,5% |
| **Classificados / indeterminados** | 944 / 56 | 94,4% / 5,6% |

Sensibilidade ao limiar (% de indeterminados):

| Limiar | Censo 2010 (este piloto) | Censo 2022 (piloto da 1ª Unidade) |
|---|---|---|
| 80% | 4,6% | 2,8% |
| 90% | 5,6% | 3,7% |
| 95% | 6,3% | 4,8% |
| 99% | 9,6% | 8,1% |

A diferença de cerca de 2 pontos percentuais pode vir da fonte (2010 contra 2022) ou do arquivo de sócios; este piloto não separa os dois efeitos.

### 4.5 Classificação na base do recorte (RN-03 a RN-05, parcial)

Aplicada às 10.366 empresas do recorte parcial, a partir da Receita filtrada (`etl/06_classificar_empresas.py`). São 18.771 vínculos de sócios, dos quais 17.403 pessoas físicas, com 3.660 primeiros nomes distintos.

**Gênero dos sócios pessoa física (RN-04, limiar de 90%):**

| Classificação | Sócios | % |
|---|---|---|
| Feminino | 5.487 | 31,5% |
| Masculino | 11.149 | 64,1% |
| Indeterminado: ambíguo | 174 | 1,0% |
| Indeterminado: nome ausente da base | 593 | 3,4% |

**Qualificações (RN-03).** As mais frequentes entre os sócios pessoa física: sócio-administrador (49) 9.825; sócio (22) 3.106; diretor (10) 1.873; administrador (05) 1.590; presidente (16) 514; conselheiro de administração (08) 414. Nenhum vínculo foi excluído por qualificação de procurador ou representante (esses dados vêm em colunas próprias de representante, descartadas). Diretor, administrador, presidente e conselheiro somam 4.391 vínculos (25,2%).

**Classificação das empresas (RN-05):**

| Classificação da empresa | RN-03 padrão (administradores contam) | RN-03 estrita (sem diretor, administrador, presidente e conselheiro) |
|---|---|---|
| Masculino, por maioria dos sócios | 4.497 (43,4%) | 3.994 (38,5%) |
| Feminino, por maioria dos sócios | 2.129 (20,5%) | 2.040 (19,7%) |
| Misto ou indeterminado: sem maioria | 1.206 (11,6%) | 1.142 (11,0%) |
| Misto ou indeterminado: com sócio PJ | 897 (8,7%) | 897 (8,7%) |
| Misto ou indeterminado: mais de um terço de indeterminados | 442 (4,3%) | 414 (4,0%) |
| Sem sócio elegível | 1.195 (11,5%) | 1.879 (18,1%) |
| **Controle definido (masculino ou feminino)** | 6.626 (63,9% do recorte) | 6.034 (58,2% do recorte) |
| Entre as definidas, % femininas | 32,1% | 33,8% |

**Decisão:** a regra padrão segue o roteiro (participação societária ou administração), e a estrita fica como análise de sensibilidade. `[CONFIRMAR com o grupo]`

**Empresas sem sócio elegível na regra padrão (1.195):** 984 são empresários individuais (natureza jurídica 2135), 69 autarquias municipais, 39 municípios, 14 órgãos públicos municipais e 14 serviços sociais autônomos. O controle dessas empresas não é inferível pela tabela de sócios.

## 5. Arquitetura, Terraform e segredos

```mermaid
flowchart TD
    subgraph FONTES["Fontes abertas"]
        A1["PNCP<br/>API de consulta, JSON"]
        A2["Receita Federal<br/>CNPJ em ZIP e CSV, via espelho"]
        A3["IBGE<br/>API de nomes, SIDRA 9605"]
        A4["Portal da Transparência<br/>CEIS e CNEP"]
    end

    subgraph LOCAL["Processamento local: Python e DuckDB (data/, fora do Git)"]
        B1["01 Coleta do PNCP<br/>NDJSON por dia, retomável"]
        B2["02 Tratamento<br/>schema tipado, deduplicação, RN-01"]
        B3["03 Recorte<br/>RN-02, top 50 órgãos, raízes de CNPJ"]
        B4["05 Filtro da Receita<br/>streaming, só as raízes do recorte"]
        B5["06 Classificação<br/>RN-03 a RN-05, id derivado RN-09"]
        B6["Parquet<br/>contratos do recorte, sócios e empresas classificados"]
    end

    subgraph NUVEM["Nuvem"]
        C0["Terraform<br/>main.tf, variables.tf, outputs.tf"]
        C1[("PostgreSQL no Aiven free<br/>modelo estrela e tabela ponte")]
        C2["Agregados materializados"]
        C3["Streamlit Cloud<br/>filtro cruzado, métrica, drill-down"]
    end

    GH["GitHub Actions<br/>ETL agendado"]
    OS["OpenSearch<br/>texto do objeto do contrato"]

    A1 --> B1 --> B2 --> B3
    B3 -->|"cnpjs_raiz.csv"| B4
    A2 -->|"streaming, sem gravar o bruto"| B4
    B4 --> B5
    A3 -->|"gênero pelo primeiro nome"| B5
    B2 --> B6
    B3 --> B6
    B5 --> B6
    B6 -->|"07 Carga, só o recorte"| C1
    A3 -->|"proxy de cor/raça por município, RN-06"| C1
    A4 -.->|"RN-08, planejado"| C1
    C1 --> C2 --> C3
    C0 -.->|"provisiona"| C1
    GH -.->|"agenda"| B1
    C1 -.->|"escopo condicional"| OS

    classDef planejado stroke-dasharray: 5 5
    class A4,GH,OS planejado
```

Linhas tracejadas: itens planejados ou de escopo condicional.

- **Infraestrutura como código:** `terraform/` (`main.tf`, `variables.tf`, `outputs.tf`) cria o serviço PostgreSQL no Aiven. Provider `aiven/aiven` 4.x (versão fixada em `.terraform.lock.hcl`), plano `free-1-1gb`.
- **Limites do plano free:** 1 CPU, 1 GB de RAM, 1 GB de disco, máximo de 20 conexões, um serviço free por organização, desligamento por inatividade.
- **Segredos:** o token do Aiven entra só por variável de ambiente (`TF_VAR_aiven_api_token`), sem valor padrão no código. A `DATABASE_URL` e o `ID_SALT` (sal do identificador do sócio) ficam no `.env`. O `.gitignore` cobre `.env`, `*.tfstate`, `*.tfstate.*`, `.terraform/` e `*.tfvars` (o repositório tem só `.example`). O `tfstate` guarda credenciais em texto claro e nunca é versionado.
- **Problemas encontrados e resolvidos:** o plano free passou de 5 GB para 1 GB, então o nome do plano mudou; erro 401 por token copiado errado; erro 403 porque a organização já tinha um PostgreSQL free (o limite é 1); erro 404 no clone limpo por `project_name` ainda com o texto de exemplo.
- **Evidências:** `docs/img/aiven_running.png` (serviço Running), `docs/terraform_apply.txt` e `docs/terraform_state.txt`. Reprovisionamento em clone limpo em 20/11/2026 (`git clone`, `terraform init`, `terraform apply`), com o serviço em Running: `docs/img/aiven_running_maquina_limpa.png` e `docs/terraform_apply_maquina_limpa.txt`.

## 6. Modelo de dados e por que relacional

Modelo estrela com 9 tabelas (`etl/sql/schema.sql`): `fato_contrato` (grão: um contrato) e as dimensões `dim_orgao`, `dim_fornecedor`, `dim_tempo`, `dim_cnae`, `dim_municipio`, `dim_modalidade`, `dim_socio`, mais a tabela ponte `ponte_empresa_socio`.

A relação empresa-sócio é muitos-para-muitos (um sócio em várias empresas, uma empresa com vários sócios), por isso ela não cabe numa dimensão comum e precisa da ponte. É ela que permite o agregado de gênero por empresa e a análise de rede. A ponte guarda também a marca `elegivel` (RN-03), para que o painel mostre a sensibilidade da regra.

O contrato do PNCP não traz modalidade de licitação. A `dim_modalidade` combina `tipoContrato` e `categoriaProcesso` (por exemplo, "Outros | Compras"). O campo `numeroControlePncpCompra` liga o contrato à compra (onde estaria a modalidade), mas a compra não foi coletada. O `fato_contrato` inclui os contratos de fornecedor PF e estrangeiro com a raiz de CNPJ nula, para que o valor total do recorte feche; nos KPIs de controle, eles aparecem como categoria própria.

**Por que relacional:** a análise é feita de junções entre entidades bem definidas, com cardinalidade conhecida, e o modelo estrela responde às agregações do painel com índice em poucas colunas. O não relacional entra só onde o dado é texto sem esquema fixo (`objetoContrato`, camada opcional).

**Orçamento de armazenamento (1 GB):**

| Camada | Onde fica |
|---|---|
| Receita bruta (37 ZIP) | nunca em disco; lida por streaming |
| Contratos tratados do ano | Parquet local (DuckDB), fora do banco |
| Receita filtrada | Parquet local; no banco só `dim_fornecedor`, `dim_socio`, `ponte` |
| `fato_contrato` | só o recorte (cerca de 100 mil linhas no ano, extrapolando as 33.672 de 120 dias); `objeto_contrato` truncado em 500 caracteres |
| Agregados do painel | materializados no banco |

Regra: o banco não passa de 600 MB, medido após cada carga pelo próprio `07_carregar_aiven.py` e por `etl/sql/budget.sql`. Os índices (`etl/sql/indices.sql`) são criados depois das cargas. `[PREENCHER: tamanho medido por tabela]`

## 7. Regras de negócio

| Regra | Enunciado resumido | Estado |
|---|---|---|
| RN-01 | CNPJ como texto de 14 caracteres; chave de junção com sócios é a raiz de 8 | implementada (`02_tratar_contratos.py`) |
| RN-02 | Entram contratos de despesa (`receita = false`), valor global maior que zero e até R$ 1 bi, assinados no recorte (2025). Contratos anulados ou cancelados não podem ser excluídos: o endpoint não traz situação do contrato | implementada (`03_recorte_cnpjs.py`), com limitações declaradas |
| RN-03 | Só sócios pessoa física com qualificação de participação ou administração (padrão); variante estrita sem diretor, administrador, presidente e conselheiro | implementada (`06`), dados parciais |
| RN-04 | Gênero pelo primeiro nome (API de nomes do IBGE), categoria dominante com 90% ou mais; senão, indeterminado | implementada (`06`), dados parciais |
| RN-05 | Controle da empresa por maioria de sócios elegíveis; misto ou indeterminado em empate, sócio PJ ou mais de um terço de indeterminados | implementada (`06`), dados parciais |
| RN-06 | Proxy de cor/raça por setor (CNAE) e município, atribuído ao contexto da empresa | Fase 2 |
| RN-07 | Concentração societária com marcação de sobreposição | Fase 2 |
| RN-08 | Sanção vigente na data de assinatura (CEIS/CNEP) | Fase 2 |
| RN-09 | CPF nunca armazenado; nome fora do banco (identificador derivado com sal); mínimo de 5 por recorte | identificador e carga sem nome implementados (`06` e `07`); mínimo de 5 no painel, Fase 2 |

**Justificativas já fechadas:**
- RN-02, receita: segundo o manual do PNCP, `receita = true` é contrato em que o órgão recebe (receita), e não contrato que paga fornecedor; 5.175 contratos (0,9%) nos dados parciais.
- RN-02, teto de R$ 1 bi: os 87 contratos acima desse valor somavam R$ 5,87 trilhões (96,6% do valor total), com valores implausíveis, até R$ 1,1 trilhão.
- RN-02, assinatura em 2025: a API filtra por data de publicação, e 102.546 contratos publicados em 2025 foram assinados em 2024.
- RN-03, padrão: o roteiro inclui quem administra; a variante estrita mede quanto a escolha pesa (4.391 vínculos de 17.403, 25,2%).

## 8. Redução de volume

| Etapa | Volume |
|---|---|
| Receita, bruto (37 ZIP) | 7,76 GB compactado (medido) |
| Receita lida no filtro (Sócios, Empresas, Estabelecimentos) | 7,45 GB compactados, 171,8 milhões de linhas (lista parcial de 10.366 raízes) |
| Receita descompactada | `[PREENCHER: saída do --consolidar]` |
| Receita após o filtro (Parquet) | `[PREENCHER: saída do --consolidar]` (130.727 linhas, 0,076% das lidas) |
| Redução | `[PREENCHER: saída do --consolidar]` |
| PNCP, JSON bruto (parcial) | 1,08 GB (137 dias) |
| PNCP, `contratos.parquet` (120 dias, 572.866 contratos) | 101,8 MB |
| PNCP, `contratos_recorte.parquet` (33.672 contratos) | 5,6 MB |
| Banco no Aiven após a carga | `[PREENCHER: saída do 07_carregar_aiven.py]` |

## 9. Achados e limitações

Limitações já conhecidas:
- **Coleta por data de publicação:** contratos assinados no fim de 2025 e publicados só em 2026 ficam de fora (viés de borda direita).
- **Sem situação do contrato:** não é possível excluir contratos anulados ou cancelados.
- **Valores concentrados:** o teto de R$ 1 bi remove só os erros grosseiros. Entre os 15 maiores contratos do recorte há valores de R$ 769 a R$ 978 milhões, com quatro contratos de exatamente R$ 900 milhões do mesmo órgão e quatro de municípios; um consórcio soma R$ 17,6 bi em 120 contratos. Não conseguimos verificar contrato por contrato. No recorte parcial (33.672 contratos), 969 (2,9%) acima de R$ 10 milhões concentram 90,8% do valor; 179 (0,5%) acima de R$ 100 milhões concentram 63,2%; 43 (0,1%) acima de R$ 500 milhões concentram 31,7%. **Decisão:** a RN-02 não muda (teto de R$ 1 bi); os KPIs de valor são sempre apresentados com e sem os contratos acima de R$ 100 milhões (pela faixa de valor do painel), o painel usa mediana e não só média, e a concentração do valor em poucos contratos é reportada como achado. `[CONFIRMAR com o grupo]`
- **Parcela e acumulado:** `valor_parcela` é nulo ou zero em 32,1% dos contratos e `valor_acumulado` em 77,3% (parcial); só `valor_global` é usado como métrica.
- **Fornecedores PF e PE** (7,6% e 0,6% dos contratos do recorte parcial) ficam fora da cadeia societária e são contados à parte.
- **Recorte por órgão:** viés para órgãos grandes.
- **Amostras da Receita no inventário** são sequenciais: dois arquivos da mesma base deram perfis diferentes (Estabelecimentos0: 50,11% ativa e 44,25% baixada; no inventário anterior, Estabelecimentos1: 15,6% e 63,1%). Os percentuais valem só para as linhas lidas.
- **O quadro societário da Receita é o de hoje;** os contratos são de 2025.
- **Gênero por contagem por cabeça,** porque o percentual de participação não consta dos dados abertos.
- **Gênero indeterminado:** 4,4% dos sócios pessoa física no recorte parcial (1,0% ambíguo e 3,4% nome ausente). Em empresas com um ou dois sócios, um único sócio indeterminado já torna a empresa `misto_indeterminado` (regra de um terço da RN-05).
- **Controle definido em 63,9% das empresas do recorte parcial.** As demais são mistas ou indeterminadas (24,6%) ou não têm sócio elegível (11,5%).
- **Empresários individuais:** 984 empresas (9,5% do recorte parcial) não têm sócio na base, porque o titular não consta da tabela de sócios. O gênero do titular poderia ser inferido do primeiro nome da razão social, mas isso não foi feito. `[CONFIRMAR com o grupo]`
- **Administradores:** 25,2% dos vínculos de sócios pessoa física são de diretor, administrador, presidente ou conselheiro, que administram e não são necessariamente donos; a variante estrita da RN-03 mostra o efeito.
- **Cor/raça por inferência ecológica** (setor e município), nunca por pessoa.
- **Fonte da Receita:** os arquivos foram lidos de um espelho (ver seção 10).

`[PREENCHER na Fase 2: achados com número]`

## 10. Reprodução

Fontes e datas de acesso:
- **PNCP:** `https://pncp.gov.br/api/consulta/v1/contratos`, acessado em `[PREENCHER: período de coleta]`.
- **Receita Federal, dados abertos do CNPJ**, competência `[CONFIRMAR: pasta do RECEITA_URL; os arquivos do espelho têm data de 18/09/2026]`, acessado em 20/11/2026. O servidor oficial estava lento ou inacessível, então os arquivos foram lidos do espelho da Casa dos Dados (`dados-abertos-rf-cnpj.casadosdados.com.br`), cópia dos arquivos da Receita. A origem dos dados continua sendo a Receita Federal. O total (37 arquivos, 7,76 GB) coincide com a medição anterior do grupo na fonte da Receita.
- Layout das colunas: `gov.br/receitafederal/dados/cnpj-metadados.pdf`.
- **IBGE:** SIDRA (Censo 2022, tabela 9605) e API de nomes (`api/v2/censos/nomes`), acessados em 20/11/2026.

Passos:
1. `python -m venv .venv`, ativar e `pip install -r requirements.txt`.
2. Copiar `.env.example` para `.env` e preencher `DATABASE_URL`, `RECEITA_URL` (com `{arquivo}` no lugar do nome do arquivo) e `ID_SALT` (gerar com `python -c "import secrets; print(secrets.token_hex(16))"` e guardar; se mudar, os identificadores dos sócios mudam).
3. `cd terraform`, copiar `terraform.tfvars.example` para `terraform.tfvars` e preencher `project_name`, definir `TF_VAR_aiven_api_token`, `terraform init`, `terraform plan`, `terraform apply` e `terraform output -raw service_uri` para a `DATABASE_URL`.
4. `cd etl`, `python aplicar_schema.py`.
5. Coleta: `python 01_coletar_pncp.py` (retomável; repetir até não haver falhas).
6. Inventário da Receita: `python 00_inventario_receita.py` e `python 00b_planilha_inventario.py`.
7. Tratamento: `python 02_tratar_contratos.py`, diagnóstico `python 02b_diagnostico.py` e recorte `python 03_recorte_cnpjs.py`.
8. Fontes do IBGE e piloto de gênero: `python t3_checar_fontes.py` e `python 04_piloto_genero.py`.
9. Filtro da Receita: `python 05_filtrar_receita.py --refazer` e `python 05_filtrar_receita.py --consolidar`.
10. Classificação de sócios e empresas: `python 06_classificar_empresas.py`.
11. Carga no banco: `python 07_carregar_aiven.py --simular`, depois `python 07_carregar_aiven.py` (use `--recarregar` para refazer).
12. `[PREENCHER na Fase 2: proxy de cor/raça, agregados, painel]`

Observação: o Windows PowerShell 5.1 exibe arquivos UTF-8 com acentos quebrados quando lidos com `Get-Content`. Os arquivos estão corretos; use `Get-Content -Encoding UTF8`.