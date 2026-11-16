"""Caminhos do projeto e convenções compartilhadas entre scripts e notebooks."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Arquivos originais, exatamente como baixados
RAW = DATA / "raw"
RAW_DATASUS = RAW / "datasus"
RAW_INMET = RAW / "inmet"

# Camadas do ETL (uma pasta de dados por camada de notebooks)
LEITURA = DATA / "01_leitura"            # bruto estruturado: tipado, consolidado, sem regra de negócio
TRATAMENTO = DATA / "02_tratamento"      # limpo, padronizado, formato longo, integrado
DISPONIBILIZACAO = DATA / "03_disponibilizacao"  # camada semântica: fatos, dimensões e métricas (CSV p/ Power BI)

FIGURAS = ROOT / "reports" / "figures"

# Período comum às duas fontes
ANO_INICIO, ANO_FIM = 2014, 2026

# Exportação para Power BI (localidade pt-BR)
CSV_POWERBI = dict(sep=";", decimal=",", encoding="utf-8-sig", index=False, date_format="%Y-%m-%d")

UF_POR_CODIGO = {
    "11": ("RO", "Rondônia", "Norte"), "12": ("AC", "Acre", "Norte"), "13": ("AM", "Amazonas", "Norte"),
    "14": ("RR", "Roraima", "Norte"), "15": ("PA", "Pará", "Norte"), "16": ("AP", "Amapá", "Norte"),
    "17": ("TO", "Tocantins", "Norte"), "21": ("MA", "Maranhão", "Nordeste"), "22": ("PI", "Piauí", "Nordeste"),
    "23": ("CE", "Ceará", "Nordeste"), "24": ("RN", "Rio Grande do Norte", "Nordeste"),
    "25": ("PB", "Paraíba", "Nordeste"), "26": ("PE", "Pernambuco", "Nordeste"), "27": ("AL", "Alagoas", "Nordeste"),
    "28": ("SE", "Sergipe", "Nordeste"), "29": ("BA", "Bahia", "Nordeste"), "31": ("MG", "Minas Gerais", "Sudeste"),
    "32": ("ES", "Espírito Santo", "Sudeste"), "33": ("RJ", "Rio de Janeiro", "Sudeste"),
    "35": ("SP", "São Paulo", "Sudeste"), "41": ("PR", "Paraná", "Sul"), "42": ("SC", "Santa Catarina", "Sul"),
    "43": ("RS", "Rio Grande do Sul", "Sul"), "50": ("MS", "Mato Grosso do Sul", "Centro-Oeste"),
    "51": ("MT", "Mato Grosso", "Centro-Oeste"), "52": ("GO", "Goiás", "Centro-Oeste"),
    "53": ("DF", "Distrito Federal", "Centro-Oeste"),
}


def garantir_pastas() -> None:
    for p in (LEITURA, TRATAMENTO, DISPONIBILIZACAO, FIGURAS):
        p.mkdir(parents=True, exist_ok=True)
