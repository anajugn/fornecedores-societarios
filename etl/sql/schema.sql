CREATE TABLE IF NOT EXISTS dim_tempo (
  sk_tempo   integer PRIMARY KEY,          -- yyyymmdd
  data       date NOT NULL,
  ano        smallint,
  mes        smallint,
  trimestre  smallint
);

CREATE TABLE IF NOT EXISTS dim_orgao (
  sk_orgao     serial PRIMARY KEY,
  orgao_cnpj   char(14) UNIQUE NOT NULL,
  razao_social text,
  esfera_id    text,
  poder_id     text
);

CREATE TABLE IF NOT EXISTS dim_municipio (
  codigo_ibge   char(7) PRIMARY KEY,
  nome          text,
  uf            char(2),
  populacao     integer,
  pct_negra     numeric(5,2),              -- preta + parda, Censo 2022 (proxy territorial, RN-06)
  pct_branca    numeric(5,2)
);

CREATE TABLE IF NOT EXISTS dim_cnae (
  cnae               char(7) PRIMARY KEY,
  descricao          text,
  pct_negra_setor    numeric(5,2),         -- RAIS/CAGED (proxy setorial, RN-06)
  pct_mulher_setor   numeric(5,2)
);

CREATE TABLE IF NOT EXISTS dim_modalidade (
  sk_modalidade serial PRIMARY KEY,
  id_origem     integer,
  nome          text
);

CREATE TABLE IF NOT EXISTS dim_fornecedor (
  cnpj_raiz     char(8) PRIMARY KEY,       -- RN-01
  razao_social  text,
  porte         text,
  natureza_juridica text,
  cnae_principal char(7),
  codigo_ibge   char(7),
  uf            char(2),
  classificacao_controle text
     CHECK (classificacao_controle IN ('feminino','masculino','misto_indeterminado','sem_socio')),  -- RN-05
  n_socios_elegiveis smallint,
  pct_indeterminados numeric(5,2)
);

CREATE TABLE IF NOT EXISTS dim_socio (
  sk_socio     serial PRIMARY KEY,
  id_derivado  text UNIQUE NOT NULL,       -- hash de máscara do CPF + nome (RN-09); nunca o CPF
  tipo         char(2) CHECK (tipo IN ('PF','PJ','ES')),
  genero       char(1) CHECK (genero IN ('F','M','I')),   -- RN-04
  confianca    numeric(4,3),
  faixa_etaria smallint
);

CREATE TABLE IF NOT EXISTS ponte_empresa_socio (   -- relação N:N
  cnpj_raiz     char(8) NOT NULL REFERENCES dim_fornecedor(cnpj_raiz),
  sk_socio      integer NOT NULL REFERENCES dim_socio(sk_socio),
  qualificacao  text NOT NULL,
  data_entrada  date,
  PRIMARY KEY (cnpj_raiz, sk_socio, qualificacao)
);

CREATE TABLE IF NOT EXISTS fato_contrato (
  numero_controle_pncp text PRIMARY KEY,
  sk_orgao       integer REFERENCES dim_orgao(sk_orgao),
  cnpj_raiz_fornecedor char(8) REFERENCES dim_fornecedor(cnpj_raiz),
  sk_tempo       integer REFERENCES dim_tempo(sk_tempo),
  sk_modalidade  integer REFERENCES dim_modalidade(sk_modalidade),
  codigo_ibge    char(7),
  valor_global   numeric(18,2),
  valor_parcela  numeric(18,2),
  prazo_dias     integer,
  objeto_contrato text,                    -- truncado em 500 caracteres na carga
  sancionado_na_assinatura boolean DEFAULT false   -- RN-08
);