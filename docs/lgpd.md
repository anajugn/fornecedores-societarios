# Parecer de LGPD e dados abertos

Projeto: Contratações Públicas e Fornecedores Societários. Rascunho de 20/11/2026, para revisão da professora. O grupo não é assessoria jurídica.

## 1. Dados tratados e finalidade

- **Contratos públicos** (PNCP): órgão, fornecedor, valor, objeto, datas.
- **Cadastro de CNPJ** (Receita Federal): empresas, estabelecimentos e quadro societário (nome, qualificação, data de entrada, faixa etária, CPF já mascarado pela Receita).
- **Tabelas agregadas** do IBGE (nomes e cor/raça por município).

Finalidade: estudo acadêmico de interesse público sobre a distribuição de recursos públicos e a composição do controle das empresas fornecedoras. O trabalho descreve padrões agregados; não avalia, nem identifica, pessoas.

## 2. Base e natureza dos dados

- Os contratos e o cadastro de CNPJ são dados abertos, publicados por força da Lei 12.527/2011 (Lei de Acesso à Informação) e do Decreto 8.777/2016 (Política de Dados Abertos).
- **Nome de sócio é dado pessoal** mesmo sendo público. O tratamento respeita a finalidade, a boa-fé e o interesse público que justificaram a publicação (LGPD, art. 7º, § 3º), e a finalidade de estudo por órgão de pesquisa com anonimização sempre que possível (art. 7º, IV). O enquadramento do grupo como estudo acadêmico fica a confirmar com a professora.
- **Cor/raça é dado pessoal sensível** (LGPD, art. 5º, II, origem racial ou étnica). Não é inferida para nenhum indivíduo.
- **Gênero** não consta da lista do art. 5º, II, mas o resultado é uma inferência estatística sobre o primeiro nome. O grupo o trata com o mesmo cuidado: nunca é exibido por pessoa.

## 3. Medidas adotadas

| Medida | Como |
|---|---|
| Minimização | Só as colunas usadas pelas regras entram no pipeline. Descartados: endereço, telefone, e-mail, CEP, dados do representante legal, país do sócio e o campo `usuarioNome` do PNCP (quem enviou o contrato, que pode ser pessoa física). |
| CPF | Nunca armazenado. A máscara fornecida pela Receita só serve para derivar o identificador do sócio. |
| Nome do sócio | Usado só em memória e em arquivos locais não versionados (`data/`), para inferir o gênero pelo primeiro nome (RN-04). **Não é carregado no banco.** O banco guarda um identificador derivado (hash). |
| Agregação mínima | Nenhum recorte do painel exibe resultado com menos de 5 sócios ou 5 empresas (RN-09), pelo mesmo princípio com que o IBGE suprime nomes de baixa frequência. |
| Fornecedor pessoa física | Fora da cadeia societária. O nome não é exibido. |
| Razão social de empresário individual | Costuma ser o nome da pessoa; não é exibida no painel. |
| Segredos e repositório | `.env`, `*.tfstate` e `data/` fora do Git; token em variável de ambiente. |

## 4. Caminho rejeitado: reidentificação por cruzamento

Existem bases com cor/raça autodeclarada e nome de pessoa física, como as de candidaturas do TSE. Cruzar o nome do sócio com essas bases permitiria atribuir cor/raça a um indivíduo, o que é reidentificação de dado sensível e foge da finalidade original da publicação. O grupo considerou e **rejeitou** esse caminho.

## 5. Alternativa adotada

Proxy ecológico (RN-06): a composição de cor/raça do município da sede (Censo 2022) e do setor CNAE (RAIS ou Novo CAGED) é atribuída ao contexto da empresa, e nunca a uma pessoa. A limitação é nomeada: o indicador descreve para onde o recurso público flui, em termos de perfil setorial e territorial, e não afirma nada sobre os sócios.

## 6. Limitações

- A inferência de gênero é probabilística. Há uma taxa de indeterminados, que é reportada.
- A contagem é por cabeça: o percentual de participação de cada sócio não consta dos dados abertos.
- O quadro societário é o atual, e os contratos são de 2025.