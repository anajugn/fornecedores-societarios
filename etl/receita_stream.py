"""Lê o CSV de dentro de um ZIP remoto em streaming. Nada vai para o disco."""
import csv
import requests
from stream_unzip import stream_unzip

# Ordem das colunas conforme o layout da Receita (conferida contra os arquivos lidos).
COLUNAS = {
    "Empresas": ["cnpj_basico", "razao_social", "natureza_juridica",
                 "qualificacao_responsavel", "capital_social", "porte", "ente_federativo"],
    "Estabelecimentos": ["cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
                         "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
                         "motivo_situacao_cadastral", "nome_cidade_exterior", "pais",
                         "data_inicio_atividade", "cnae_principal", "cnae_secundaria",
                         "tipo_logradouro", "logradouro", "numero", "complemento", "bairro",
                         "cep", "uf", "municipio", "ddd1", "telefone1", "ddd2", "telefone2",
                         "ddd_fax", "fax", "correio_eletronico", "situacao_especial",
                         "data_situacao_especial"],
    "Socios": ["cnpj_basico", "identificador_socio", "nome_socio", "cnpj_cpf_socio",
               "qualificacao_socio", "data_entrada_sociedade", "pais", "representante_legal",
               "nome_representante", "qualificacao_representante_legal", "faixa_etaria"],
}


def linhas_zip(url, encoding="latin-1", contador=None):
    """Gera as linhas do CSV. Se `contador` for um dict com as chaves 'compactado' e
    'descompactado', ele é incrementado com os bytes baixados e descompactados."""
    with requests.get(url, stream=True, timeout=(30, 300)) as r:
        r.raise_for_status()

        def pedacos():
            for chunk in r.iter_content(chunk_size=1 << 20):
                if contador is not None:
                    contador["compactado"] += len(chunk)
                yield chunk

        for _nome, _tam, partes in stream_unzip(pedacos()):
            resto = b""
            for parte in partes:
                if contador is not None:
                    contador["descompactado"] += len(parte)
                resto += parte
                *linhas, resto = resto.split(b"\n")
                for linha in linhas:
                    yield linha.decode(encoding).rstrip("\r")
            if resto:
                yield resto.decode(encoding).rstrip("\r")


def registros_zip(url, n_colunas, contador=None):
    for row in csv.reader(linhas_zip(url, contador=contador), delimiter=";", quotechar='"'):
        if len(row) != n_colunas:
            raise ValueError(f"esperava {n_colunas} colunas, veio {len(row)}: confira o PDF de metadados")
        yield row