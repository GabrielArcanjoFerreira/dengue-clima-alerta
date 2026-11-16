"""
Calendário de semanas epidemiológicas (padrão do Ministério da Saúde / MMWR).

A semana epidemiológica vai de domingo a sábado. A semana 1 do ano termina no primeiro
sábado de janeiro que tenha pelo menos 4 dias no ano — equivalentemente, começa no domingo
imediatamente anterior (ou igual) a 4 de janeiro. Um ano epidemiológico tem 52 ou 53 semanas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def inicio_ano_epi(ano: int) -> pd.Timestamp:
    jan4 = pd.Timestamp(year=ano, month=1, day=4)
    return jan4 - pd.Timedelta(days=(jan4.weekday() + 1) % 7)  # volta até o domingo


def semanas_no_ano(ano: int) -> int:
    return int((inicio_ano_epi(ano + 1) - inicio_ano_epi(ano)).days // 7)


def calendario(ano_ini: int, ano_fim: int) -> pd.DataFrame:
    """Uma linha por semana epidemiológica, com datas de início/fim."""
    linhas = []
    for ano in range(ano_ini, ano_fim + 1):
        ini = inicio_ano_epi(ano)
        for s in range(1, semanas_no_ano(ano) + 1):
            d0 = ini + pd.Timedelta(weeks=s - 1)
            linhas.append((ano * 100 + s, ano, s, d0, d0 + pd.Timedelta(days=6)))
    return pd.DataFrame(linhas, columns=["id_semana", "ano_epi", "semana_epi", "data_inicio", "data_fim"])


def data_para_semana(datas: pd.Series) -> pd.DataFrame:
    """Converte datas em (ano_epi, semana_epi, id_semana) de forma vetorizada."""
    datas = pd.to_datetime(datas).dt.normalize()
    anos = np.arange(datas.dt.year.min() - 1, datas.dt.year.max() + 2)
    inicios = pd.Series([inicio_ano_epi(int(a)) for a in anos], index=anos)
    ano = datas.dt.year.to_numpy()
    ini_ano = inicios.reindex(ano).to_numpy()
    ini_prox = inicios.reindex(ano + 1).to_numpy()
    d = datas.to_numpy()
    ano_epi = np.where(d < ini_ano, ano - 1, np.where(d >= ini_prox, ano + 1, ano))
    ini_epi = inicios.reindex(ano_epi).to_numpy()
    semana = ((d - ini_epi) // np.timedelta64(7, "D")).astype(int) + 1
    return pd.DataFrame({"ano_epi": ano_epi, "semana_epi": semana, "id_semana": ano_epi * 100 + semana},
                        index=datas.index)
