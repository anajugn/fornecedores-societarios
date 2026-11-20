CREATE INDEX IF NOT EXISTS ix_fato_forn   ON fato_contrato(cnpj_raiz_fornecedor);
CREATE INDEX IF NOT EXISTS ix_fato_orgao  ON fato_contrato(sk_orgao);
CREATE INDEX IF NOT EXISTS ix_fato_tempo  ON fato_contrato(sk_tempo);
CREATE INDEX IF NOT EXISTS ix_ponte_socio ON ponte_empresa_socio(sk_socio);
CREATE INDEX IF NOT EXISTS ix_forn_cnae   ON dim_fornecedor(cnae_principal);