"""
Camada de LEITURA do INMET: descompacta os .zip anuais e grava os CSVs horários em Parquet.

Entrada : data/raw/inmet/zip/{ano}.zip  (um CSV horário por estação automática)
Saídas  : data/01_leitura/inmet/
            horario/ano={ano}/inmet_horario_{ano}.parquet  -> todas as estações do ano
            estacoes_por_ano.csv                           -> metadados de cada CSV (estação x ano)

Só o necessário para LER os arquivos — regras de negócio e limpeza ficam na camada de tratamento:
  * cabeçalho de 8 linhas com metadados da estação -> colunas;
  * nomes das 17 variáveis padronizados (o layout mudou em 2019, mas a ordem das colunas é a mesma);
  * decimal com vírgula -> float; sentinela -9999 e campos vazios -> NaN (são marcadores de
    "sem medição" do próprio INMET, não valores);
  * data + hora (UTC) -> timestamp `datahora_utc`.
"""
from __future__ import annotations

import argparse
import io
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from config import LEITURA, RAW_INMET

DIR_ZIP = RAW_INMET / "zip"
DIR_OUT = LEITURA / "inmet"
DIR_HORARIO = DIR_OUT / "horario"

# Ordem fixa das 17 medições (igual em todos os anos)
VARIAVEIS = [
    "precipitacao_mm",          # PRECIPITAÇÃO TOTAL, HORÁRIO (mm)
    "pressao_mb",               # PRESSAO ATMOSFERICA AO NIVEL DA ESTACAO, HORARIA (mB)
    "pressao_max_mb",           # PRESSÃO ATMOSFERICA MAX.NA HORA ANT. (AUT) (mB)
    "pressao_min_mb",           # PRESSÃO ATMOSFERICA MIN. NA HORA ANT. (AUT) (mB)
    "radiacao_kjm2",            # RADIACAO GLOBAL (KJ/m²)
    "temp_ar_c",                # TEMPERATURA DO AR - BULBO SECO, HORARIA (°C)
    "temp_orvalho_c",           # TEMPERATURA DO PONTO DE ORVALHO (°C)
    "temp_max_c",               # TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C)
    "temp_min_c",               # TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C)
    "orvalho_max_c",            # TEMPERATURA ORVALHO MAX. NA HORA ANT. (AUT) (°C)
    "orvalho_min_c",            # TEMPERATURA ORVALHO MIN. NA HORA ANT. (AUT) (°C)
    "umidade_max_pct",          # UMIDADE REL. MAX. NA HORA ANT. (AUT) (%)
    "umidade_min_pct",          # UMIDADE REL. MIN. NA HORA ANT. (AUT) (%)
    "umidade_pct",              # UMIDADE RELATIVA DO AR, HORARIA (%)
    "vento_direcao_graus",      # VENTO, DIREÇÃO HORARIA (gr) (° (gr))
    "vento_rajada_ms",          # VENTO, RAJADA MAXIMA (m/s)
    "vento_velocidade_ms",      # VENTO, VELOCIDADE HORARIA (m/s)
]
COLUNAS_CSV = ["data", "hora", *VARIAVEIS]


def _num(txt: str) -> float | None:
    try:
        return float(txt.strip().replace(",", "."))
    except ValueError:
        return None


def _data_iso(txt: str) -> str:
    """Fundação vem como 'YYYY-MM-DD' (até 2018) ou 'DD/MM/YY' (2019+)."""
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%d/%m/%Y"):
        try:
            return pd.to_datetime(txt.strip(), format=fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return txt.strip()


def ler_metadados(linhas: list[str]) -> dict:
    """As 8 primeiras linhas: REGIÃO, UF, ESTAÇÃO, CÓDIGO, LAT, LON, ALT, FUNDAÇÃO (ordem fixa)."""
    v = [l.split(";", 1)[1].strip().rstrip(";") if ";" in l else "" for l in linhas[:8]]
    return {
        "regiao": v[0], "uf": v[1], "estacao": v[2], "codigo_wmo": v[3],
        "latitude": _num(v[4]), "longitude": _num(v[5]), "altitude": _num(v[6]),
        "data_fundacao": _data_iso(v[7]),
    }


def ler_csv_estacao(conteudo: bytes) -> tuple[dict, pd.DataFrame]:
    linhas = conteudo.decode("latin1").splitlines()
    meta = ler_metadados(linhas)
    df = pd.read_csv(
        io.StringIO("\n".join(linhas[9:])),  # pula metadados (8) + cabeçalho (1)
        sep=";", header=None, usecols=range(len(COLUNAS_CSV)), names=COLUNAS_CSV,
        decimal=",", na_values=["-9999", "-9999,0", "-9999.0", ""], keep_default_na=False,
        dtype={"data": str, "hora": str}, engine="c",
    )
    data = pd.to_datetime(df["data"].str.replace("/", "-", regex=False), format="%Y-%m-%d", errors="coerce")
    hora = pd.to_numeric(df["hora"].str.slice(0, 2), errors="coerce")
    df.insert(0, "datahora_utc", data + pd.to_timedelta(hora, unit="h"))
    df = df.drop(columns=["data", "hora"]).dropna(subset=["datahora_utc"])
    for c in VARIAVEIS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    return meta, df


def processar_ano(zip_path: Path) -> pd.DataFrame:
    """Lê todos os CSVs de um ano, grava o Parquet horário e devolve os metadados das estações."""
    ano = int(zip_path.stem)
    metas, partes = [], []
    with zipfile.ZipFile(zip_path) as z:
        for nome in (n for n in z.namelist() if n.lower().endswith(".csv")):
            meta, df = ler_csv_estacao(z.read(nome))
            df.insert(0, "codigo_wmo", meta["codigo_wmo"])
            partes.append(df)
            metas.append({
                "ano": ano, **meta, "arquivo_origem": Path(nome).name, "n_registros": len(df),
                "inicio_utc": df["datahora_utc"].min(), "fim_utc": df["datahora_utc"].max(),
            })
    horario = pd.concat(partes, ignore_index=True)
    horario["codigo_wmo"] = horario["codigo_wmo"].astype("category")
    destino = DIR_HORARIO / f"ano={ano}"
    destino.mkdir(parents=True, exist_ok=True)
    for f in destino.glob("*.parquet"):
        f.unlink()
    horario.to_parquet(destino / f"inmet_horario_{ano}.parquet", index=False, compression="zstd")
    return pd.DataFrame(metas)


def processar(anos: list[int] | None = None, workers: int = 4) -> pd.DataFrame:
    zips = sorted(DIR_ZIP.glob("*.zip"))
    if anos:
        zips = [z for z in zips if int(z.stem) in anos]
    if not zips:
        raise FileNotFoundError(f"Nenhum zip em {DIR_ZIP}. Rode antes o download do INMET.")
    DIR_OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        metas = pd.concat(list(ex.map(processar_ano, zips)), ignore_index=True)
    metas = metas.sort_values(["codigo_wmo", "ano"]).reset_index(drop=True)
    metas.to_csv(DIR_OUT / "estacoes_por_ano.csv", sep=";", index=False, encoding="utf-8")
    return metas


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--anos", type=int, nargs="*")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    m = processar(a.anos, a.workers)
    print(f"{m['codigo_wmo'].nunique()} estações, {len(m)} arquivos estação-ano -> {DIR_OUT}")
