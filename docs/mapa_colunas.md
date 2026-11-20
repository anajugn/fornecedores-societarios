# Mapa de colunas: o que entra, o que sai e por quê

Atualizado em 20/11/2026. Os nomes dos campos do PNCP vêm do JSON real; as colunas da Receita seguem o layout oficial (`gov.br/receitafederal/dados/cnpj-metadados.pdf`), conferido contra os arquivos lidos.

## PNCP, `/v1/contratos` (43 campos no retorno)

| Campo | Destino | Uso |
|---|---|---|
| `numeroControlePNCP` | `numero_controle_pncp` | chave de deduplicação; PK do fato |
| `numeroControlePncpCompra` | `numero_controle_pncp_compra` | liga à compra (onde estaria a modalidade, não coletada) |
| `niFornecedor`, `tipoPessoa` | `cnpj_raiz_fornecedor` (só PJ com 14 dígitos), `tipo_pessoa` (PJ, PF, PE) | RN-01, chave com a Receita |
| `nomeRazaoSocialFornecedor` | `nome_fornecedor` | exibição só de PJ |
| `valorGlobal` | `valor_global` | métrica principal; RN-02 |
| `valorInicial`, `valorParcela`, `valorAcumulado` | `valor_*` | métricas secundárias; `[a medir: % zerado]` |
| `receita` | `receita` | RN-02 (exclui `true`) |
| `dataAssinatura` | `data_assinatura` | RN-02, RN-08 |
| `dataPublicacaoPncp` | `data_publicacao` | partição e controle de coleta |
| `dataVigenciaInicio`, `dataVigenciaFim` | `data_vigencia_*` | `prazo_dias` |
| `dataAtualizacaoGlobal` | `data_atualizacao_global` | desempate na deduplicação |
| `orgaoEntidade.*` | `dim_orgao` | quem contrata |
| `unidadeOrgao.ufSigla`, `.municipioNome`, `.codigoIbge` | município do órgão | filtros do painel |
| `tipoContrato`, `categoriaProcesso` | `dim_modalidade` (substituto) | o contrato não traz modalidade de licitação |
| `objetoContrato` | `objeto_contrato` | texto livre; drill-down e busca |

**Não lidos** (22 campos): `usuarioNome` (quem enviou o contrato, pode ser pessoa física), `informacaoComplementar`, `processo`, `numeroContratoEmpenho`, `anoContrato`, `sequencialContrato`, `numeroRetificacao`, `numeroParcelas`, `temRemanejamento`, `emendaParlamentar`, `frutoAdesao`, `identificadorCipi`, `urlCipi`, `orgaoSubRogado`, `unidadeSubRogada`, `codigoPaisFornecedor`, `numeroControlePncpAta`, os três campos de subcontratada, `unidadeOrgao.ufNome`, `.nomeUnidade` e `.codigoUnidade`. Nenhum serve às perguntas Q1 a Q3.

## Receita Federal

| Arquivo | Usadas | Descartadas |
|---|---|---|
| Sócios (11 colunas) | `cnpj_basico` (chave), `identificador_socio` (1 PJ, 2 PF, 3 estrangeiro), `nome_socio` (só o 1º nome, em memória, para a RN-04), `cnpj_cpf_socio` (só a máscara, para o id derivado), `qualificacao_socio` (RN-03), `data_entrada_sociedade`, `faixa_etaria` | `pais` (99,4% vazio), `representante_legal` (vem como `***000000**` quando não há), `nome_representante` (97,0% vazio), `qualificacao_representante_legal` |
| Empresas (7) | `cnpj_basico`, `razao_social`, `natureza_juridica`, `porte`, `capital_social` | `qualificacao_responsavel`, `ente_federativo` |
| Estabelecimentos (30) | `cnpj_basico`, `cnpj_ordem`, `cnpj_dv`, `identificador_matriz_filial` (usar a matriz), `situacao_cadastral`, `cnae_principal`, `uf`, `municipio` | `nome_fantasia`, `cnae_secundaria`, endereço (`tipo_logradouro`, `logradouro`, `numero`, `complemento`, `bairro`, `cep`), telefones e fax, `correio_eletronico`, `pais`, `nome_cidade_exterior`, datas e motivo de situação |
| Domínio | Cnaes, Municípios, Naturezas, Qualificações | Motivos, Países, Simples |

Atenção: o código de município da Receita (4 dígitos) não é o código IBGE (7 dígitos). A tradução usa nome e UF, a partir da tabela de municípios da Receita e da API de localidades do IBGE.

## Fontes complementares

| Uso | Fonte | Chave |
|---|---|---|
| Gênero (RN-04) | API de nomes do IBGE | primeiro nome normalizado (maiúsculas, sem acento) |
| Cor/raça territorial (RN-06) | SIDRA, Censo 2022, tabela 9605 `[CONFIRMAR]` | código IBGE do município (7 dígitos) |
| Cor/raça setorial (RN-06) | RAIS ou Novo CAGED `[escopo condicional]` | CNAE |