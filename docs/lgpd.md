# Parecer de LGPD do projeto

Análise do grupo, de caráter acadêmico. Não é parecer jurídico.

## 1. Finalidade e base
- **Finalidade:** estudo estatístico sobre quem controla as empresas que recebem dinheiro público, em trabalho de Big Data e Analytics.
- **Dados de origem públicos:** contratos do PNCP (Lei 14.133/2021, publicidade obrigatória) e cadastro CNPJ da Receita Federal (dados abertos).
- **Enquadramento:** tratamos o projeto como de fins exclusivamente acadêmicos (LGPD, art. 4º, II, "b"), observando mesmo assim os princípios do art. 6º (finalidade, adequação, necessidade) e a regra do art. 7º, § 3º, para dados de acesso público.

## 2. Dados pessoais envolvidos
| Dado | Origem | Tratamento |
|---|---|---|
| Nome e máscara do CPF de sócios (pessoas físicas) | Receita | só em memória e em arquivos locais em `data/`; nunca no banco, no Git ou no painel |
| Primeiro nome do sócio | Receita | consultado na API de nomes do IBGE; só o primeiro nome vai à API; o cache local guarda nome e frequência |
| Gênero inferido | derivado | guardado como F, M ou I, com a confiança |
| Identificador do sócio | derivado | SHA-256 de `ID_SALT` + máscara do CPF + nome completo normalizado, 16 caracteres |
| Razão social de empresário individual | Receita | substituída por texto genérico no banco, porque contém o nome da pessoa |
| Raiz de CNPJ, razão social de empresas, valores de contrato | PNCP e Receita | dados de pessoas jurídicas, públicos, mostrados no painel |

## 3. Medidas de minimização e proteção
1. O banco não tem coluna de nome nem de CPF. Dois testes automáticos (`tests/test_regras.py`) falham se aparecer coluna com "nome" ou "cpf", ou valor com formato de CPF nos Parquet de saída.
2. O sócio só existe no banco como hash com sal. O sal está no `.env`, fora do Git. Sem o sal e os dados de origem, não há como recuperar a pessoa a partir do banco.
3. A classe de controle (feminino, masculino, misto) é calculada por empresa, mas o painel nunca a mostra por empresa: só agregados.
4. O painel oculta qualquer grupo com menos de 5 fornecedores (RN-09), inclusive no drill-down.
5. Segredos (token do Aiven, `DATABASE_URL`, `ID_SALT`) ficam em variáveis de ambiente e em Secrets. Um token exposto em tela foi revogado.
6. O banco é de acesso restrito por credencial; o painel público lê dados já agregados na tela, sem exportação de linhas por sócio.

## 4. O que o projeto não faz
- **Não infere nem armazena cor/raça de pessoas.** A leitura racial é um proxy territorial: o percentual de pretos e pardos do município do fornecedor (Censo 2022). Cor/raça é dado pessoal sensível (art. 5º, II) e foi evitado por desenho.
- **Não cruza com o TSE.** O cadastro de candidaturas traz cor/raça autodeclarada ligada a nome; cruzá-lo permitiria atribuir cor/raça a pessoas reais. Foi rejeitado.
- **Não identifica pessoas no painel.** Sócios aparecem só como identificador anônimo, e o painel não os lista.

## 5. Riscos residuais
| Risco | Tratamento |
|---|---|
| Gênero inferido pelo nome pode errar e reforçar estereótipos | uso só agregado; indeterminados declarados (4,3%); limiar de 90%; limitação no README |
| Reidentificação combinando filtros do painel | mínimo de 5 fornecedores por grupo; classe de controle nunca por empresa |
| Homônimos no identificador do sócio | declarado como limitação; hash inclui a máscara do CPF |
| Arquivos locais com nomes de sócios (`data/interim/receita_filtrada`) | fora do Git; disco do grupo; apagar ao fim da disciplina |
| Leitura causal do proxy racial (falácia ecológica) | aviso fixo na aba Interseccional e no README |
| Espelho de terceiros como fonte da Receita | declarado; a origem é a Receita Federal |

## 6. Retenção
Os arquivos de `data/` e o banco do Aiven existem só para a disciplina. Após a entrega e a avaliação: apagar `data/`, destruir o serviço (`terraform destroy`) e revogar tokens.