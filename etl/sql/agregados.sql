-- Agregados materializados (RN-09: grupos cruzados só com 5+ fornecedores).
-- Recriados do zero a cada execução de etl/09_teste_comparativo.py, depois da carga.

DROP MATERIALIZED VIEW IF EXISTS mv_valor_por_classe, mv_genero_por_uf,
    mv_genero_por_faixa_racial, mv_fornecedor_valor, mv_socios_compartilhados;

CREATE MATERIALIZED VIEW mv_valor_por_classe AS
SELECT f.classificacao_controle AS classe,
       count(*) AS n_contratos,
       count(DISTINCT c.cnpj_raiz_fornecedor) AS n_fornecedores,
       sum(c.valor_global) AS valor_total,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_global) AS valor_mediano
FROM fato_contrato c
JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
WHERE c.valor_global > 0
GROUP BY 1;

CREATE MATERIALIZED VIEW mv_genero_por_uf AS
SELECT f.uf AS uf_fornecedor, f.classificacao_controle AS classe,
       count(*) AS n_contratos,
       count(DISTINCT c.cnpj_raiz_fornecedor) AS n_fornecedores,
       sum(c.valor_global) AS valor_total,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_global) AS valor_mediano
FROM fato_contrato c
JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
WHERE c.valor_global > 0
GROUP BY 1, 2
HAVING count(DISTINCT c.cnpj_raiz_fornecedor) >= 5;

CREATE MATERIALIZED VIEW mv_genero_por_faixa_racial AS
SELECT CASE WHEN m.pct_negra < 30 THEN 'até 30%'
            WHEN m.pct_negra < 50 THEN '30% a 50%'
            WHEN m.pct_negra < 70 THEN '50% a 70%'
            ELSE '70% ou mais' END AS faixa_negra,
       f.classificacao_controle AS classe,
       count(*) AS n_contratos,
       count(DISTINCT c.cnpj_raiz_fornecedor) AS n_fornecedores,
       sum(c.valor_global) AS valor_total,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY c.valor_global) AS valor_mediano
FROM fato_contrato c
JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
JOIN dim_municipio m  ON m.codigo_ibge = f.codigo_ibge
WHERE c.valor_global > 0 AND m.pct_negra IS NOT NULL
GROUP BY 1, 2
HAVING count(DISTINCT c.cnpj_raiz_fornecedor) >= 5;

-- valor por fornecedor (concentração: top 10, Gini, HHI). Sem a classe de controle, de propósito.
CREATE MATERIALIZED VIEW mv_fornecedor_valor AS
SELECT c.cnpj_raiz_fornecedor AS cnpj_raiz,
       count(*) AS n_contratos,
       sum(c.valor_global) AS valor_total
FROM fato_contrato c
JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
WHERE c.valor_global > 0
GROUP BY 1;

-- concentração societária (RN-07): em quantos fornecedores do recorte cada sócio aparece (5 = "5 ou mais")
CREATE MATERIALIZED VIEW mv_socios_compartilhados AS
WITH forn AS (
    SELECT DISTINCT cnpj_raiz_fornecedor AS cnpj_raiz
    FROM fato_contrato
    WHERE cnpj_raiz_fornecedor IS NOT NULL AND valor_global > 0),
por_socio AS (
    SELECT p.sk_socio, count(DISTINCT p.cnpj_raiz) AS n
    FROM ponte_empresa_socio p
    JOIN forn USING (cnpj_raiz)
    WHERE p.elegivel
    GROUP BY 1)
SELECT least(n, 5) AS n_fornecedores_do_socio, count(*) AS n_socios
FROM por_socio
GROUP BY 1;