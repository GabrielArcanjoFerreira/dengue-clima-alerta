"""
Coleta FOCADA das tabulações de DENGUE (SINAN) no TabNet/DATASUS.

Formulário: https://tabnet.datasus.gov.br/cgi/deftohtm.exe?sinannet/cnv/denguebbr.def

Pergunta central do projeto: o clima (chuva, temperatura, umidade) antecipa a explosão de
casos de dengue? -> base para uma CitizenTech de alerta precoce por município.

O formulário oferece 47 linhas x 34 colunas x 13 anos x 57 filtros. Em vez de varrer as
combinações, o catálogo registra TODAS as opções e só as tabulações úteis à pergunta são baixadas:

  0. CATÁLOGO         – todas as configurações do formulário + notas da fonte (dicionário de dados).
  1. MUNICÍPIO x SEMANA – município de residência x semana epidemiológica dos 1os sintomas,
                         1 arquivo por ano (2014-2026). NÚCLEO do cruzamento com o INMET.
  2. CONTEXTO ANUAL    – região, UF, capital e município de residência x ano + semana x ano
                         (dimensionar o problema, ranking territorial, sazonalidade nacional).
  3. PERFIL/GRAVIDADE  – ano x faixa etária, sexo, raça, classificação final, evolução,
                         hospitalização e sorotipo; faixa etária x evolução e x hospitalização
                         (persona: quem adoece e quem agrava; sorotipo como fator não climático).
  4. DESIGUALDADE      – municípios classificados como "extrema pobreza" x ano (ODS 10).
  5. POPULAÇÃO         – população residente por município x ano (2014-2025), estimativas
                         SVS/IBGE no próprio TabNet -> denominador da incidência por 100 mil hab.

Todas as tabulações usam LOCAL DE RESIDÊNCIA (recomendação da fonte para incidência) e
ANO/SEMANA EPIDEMIOLÓGICA DOS 1os SINTOMAS (é assim que os arquivos anuais são separados).

Uso:
    python src/download_datasus.py                  # tudo (o que já existe é pulado)
    python src/download_datasus.py --conjuntos 1    # só alguns conjuntos
    python src/download_datasus.py --dry-run        # lista as consultas sem executar
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from config import RAW_DATASUS as RAW, ROOT
from tabnet import NAO_ATIVA, TODAS, ErroTabNet, consultar, formulario_de_dict, ler_formulario

DEF_PATH = "sinannet/cnv/denguebbr.def"
DEF_POPULACAO = "ibge/cnv/popsvs2024br.def"  # estimativas populacionais por município 2000-2025
DIR_CATALOGO = RAW / "catalogo"
DIR_TABNET = RAW / "tabnet"
MANIFESTO = DIR_TABNET / "manifesto.csv"

# Variáveis do formulário (valores exatos do TabNet)
ANO_EPI = "Ano_epidem._1º_Sintomas(s)"
SEMANA_EPI = "Semana_epidem._1º_Sintomas(s)"
REGIAO_RES = "Região_de_residência"
UF_RES = "UF_de_residência"
CAPITAL_RES = "Capital_de_residência"
MUNICIPIO_RES = "Município_de_residência"
FAIXA_ETARIA = "Faixa_Etária"
FILTRO_EXTREMA_POBREZA = "SMunic_extrem_pobreza_(resid)"


def slug(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")


def opcao(opcoes, prefixo: str) -> str:
    """Valor exato de uma opção a partir do prefixo (alguns nomes têm '_' de preenchimento)."""
    achadas = [o.valor for o in opcoes if o.valor.startswith(prefixo)]
    if len(achadas) != 1:
        raise KeyError(f"opção '{prefixo}' ambígua ou inexistente: {achadas}")
    return achadas[0]


@dataclass
class Consulta:
    conjunto: int
    arquivo: Path
    linha: str
    coluna: str = NAO_ATIVA
    arquivos: list[str] = field(default_factory=list)
    filtros: dict[str, list[str]] = field(default_factory=dict)
    exibir_zeradas: bool = False
    form: str = "dengue"  # qual formulário TabNet atende a consulta


def ano_do_arquivo(dbf: str) -> int:
    return 2000 + int(re.search(r"(\d{2})\.dbf$", dbf).group(1))


def montar_consultas(form) -> list[Consulta]:
    todos = [a.valor for a in form.arquivos]
    c: list[Consulta] = []

    # 1. Núcleo: município de residência x semana epidemiológica, 1 arquivo por ano.
    #    exibir_zeradas=True -> todos os municípios aparecem (painel completo, sem buracos).
    d1 = DIR_TABNET / "01_municipio_semana"
    for arq in todos:
        c.append(Consulta(1, d1 / f"{ano_do_arquivo(arq)}.csv", MUNICIPIO_RES, SEMANA_EPI, [arq], exibir_zeradas=True))

    # 2. Contexto anual (todos os anos numa consulta só)
    d2 = DIR_TABNET / "02_contexto_anual"
    for lin, nome in [(REGIAO_RES, "regiao_residencia"), (UF_RES, "uf_residencia"),
                      (CAPITAL_RES, "capital_residencia"), (MUNICIPIO_RES, "municipio_residencia"),
                      (SEMANA_EPI, "semana_epidemiologica")]:
        c.append(Consulta(2, d2 / f"{nome}_x_ano.csv", lin, ANO_EPI, todos))

    # 3. Perfil e gravidade
    d3 = DIR_TABNET / "03_perfil_gravidade"
    evolucao = opcao(form.colunas, "Evolução")
    hospitalizacao = opcao(form.colunas, "Ocorreu_hospitalização")
    for prefixo in ("Faixa_Etária", "Sexo", "Raça", "Class._Final", "Evolução", "Ocorreu_hospitalização", "Sorotipo"):
        col = opcao(form.colunas, prefixo)
        c.append(Consulta(3, d3 / f"ano_x_{slug(prefixo)}.csv", ANO_EPI, col, todos))
    for col in (evolucao, hospitalizacao):
        c.append(Consulta(3, d3 / f"faixa_etaria_x_{slug(col)}.csv", FAIXA_ETARIA, col, todos))

    # 4. Desigualdade: municípios em extrema pobreza (atributo só disponível como filtro)
    d4 = DIR_TABNET / "04_desigualdade"
    sim = next(o.valor for o in form.selecoes[FILTRO_EXTREMA_POBREZA] if o.rotulo == "Sim")
    c.append(Consulta(4, d4 / "municipios_extrema_pobreza_x_ano.csv", MUNICIPIO_RES, ANO_EPI, todos,
                      {FILTRO_EXTREMA_POBREZA: [sim]}))
    return c


def montar_consultas_populacao(form_pop) -> list[Consulta]:
    """5. População residente por município x ano, nos mesmos anos do SINAN (2026 ainda não publicado)."""
    anos = [o.valor for o in form_pop.arquivos if 14 <= int(re.search(r"(\d{2})\.dbf$", o.valor).group(1)) <= 26]
    return [Consulta(5, DIR_TABNET / "05_populacao" / "populacao_municipio_x_ano.csv",
                     "Município", "Ano", anos, form="populacao")]


def salvar_catalogo(form, html_form: str) -> None:
    DIR_CATALOGO.mkdir(parents=True, exist_ok=True)
    (DIR_CATALOGO / "formulario_dengue.html").write_text(html_form, encoding="utf-8")
    (DIR_CATALOGO / "notas_fonte.txt").write_text(form.notas + "\n", encoding="utf-8")

    cat = {
        "fonte": form.url_form,
        "def_path": form.def_path,
        "titulo": form.titulo,
        "notas": form.notas,
        "coletado_em": datetime.now().isoformat(timespec="seconds"),
        "linhas": [asdict(o) for o in form.linhas],
        "colunas": [asdict(o) for o in form.colunas],
        "conteudos": [asdict(o) for o in form.conteudos],
        "arquivos": [asdict(o) for o in form.arquivos],
        "selecoes": {k: [asdict(o) for o in v] for k, v in form.selecoes.items()},
    }
    (DIR_CATALOGO / "catalogo_configuracoes.json").write_text(json.dumps(cat, ensure_ascii=False, indent=2), encoding="utf-8")

    # Visão consolidada: em que papéis cada variável aparece
    lin = {o.valor: o.rotulo for o in form.linhas}
    col = {o.valor: o.rotulo for o in form.colunas if o.valor != NAO_ATIVA}
    fil = {k[1:]: k for k in form.selecoes}  # nome sem o prefixo "S"
    nomes = list(dict.fromkeys([*lin, *col, *fil]))
    with open(DIR_CATALOGO / "dimensoes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["variavel", "rotulo", "como_linha", "como_coluna", "como_filtro", "n_categorias_filtro"])
        for n in nomes:
            rot = lin.get(n) or col.get(n) or n.replace("_", " ").strip()
            ncat = len(form.selecoes[fil[n]]) - 1 if n in fil else ""
            w.writerow([n, rot, int(n in lin), int(n in col), int(n in fil), ncat])

    with open(DIR_CATALOGO / "categorias_filtros.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["filtro", "valor", "rotulo"])
        for k, opcoes in form.selecoes.items():
            for o in opcoes:
                if o.valor != TODAS:
                    w.writerow([k[1:], o.valor, o.rotulo])

    with open(DIR_CATALOGO / "periodos.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["arquivo", "ano_epidemiologico"])
        for o in form.arquivos:
            w.writerow([o.valor, o.rotulo])


_lock = threading.Lock()
CAMPOS_MANIFESTO = [
    "conjunto", "arquivo", "linha", "coluna", "arquivos", "filtros", "exibir_zeradas",
    "n_linhas", "n_colunas", "total_casos", "segundos", "coletado_em", "status", "erro",
]


def carregar_manifesto() -> dict[str, dict]:
    if not MANIFESTO.exists():
        return {}
    with open(MANIFESTO, encoding="utf-8") as f:
        return {r["arquivo"]: r for r in csv.DictReader(f, delimiter=";")}


def gravar_manifesto(reg: dict[str, dict]) -> None:
    MANIFESTO.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFESTO.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS_MANIFESTO, delimiter=";")
        w.writeheader()
        for k in sorted(reg):
            w.writerow(reg[k])
    tmp.replace(MANIFESTO)


def _total(csv_txt: str) -> str:
    for l in reversed(csv_txt.strip().splitlines()):
        if l.startswith('"Total"'):
            return l.rsplit(";", 1)[-1]
    return ""


def executar(c: Consulta, forms: dict, reg: dict[str, dict], atualizacoes: dict) -> str:
    rel = str(c.arquivo.relative_to(ROOT))
    base = {
        "conjunto": c.conjunto, "arquivo": rel, "linha": c.linha, "coluna": c.coluna,
        "arquivos": ",".join(c.arquivos), "filtros": json.dumps(c.filtros, ensure_ascii=False),
        "exibir_zeradas": int(c.exibir_zeradas),
    }
    session = requests.Session()
    try:
        res = consultar(forms[c.form], c.linha, c.coluna, c.arquivos, filtros=c.filtros,
                        exibir_zeradas=c.exibir_zeradas, session=session)
        c.arquivo.parent.mkdir(parents=True, exist_ok=True)
        tmp = c.arquivo.with_suffix(".part")
        tmp.write_text(res.csv, encoding="utf-8")
        tmp.replace(c.arquivo)
        linhas = res.csv.strip().splitlines()
        reg_item = {**base, "n_linhas": len(linhas) - 1, "n_colunas": linhas[0].count(";") + 1,
                    "total_casos": _total(res.csv), "segundos": f"{res.segundos:.1f}",
                    "coletado_em": datetime.now().isoformat(timespec="seconds"), "status": "ok", "erro": ""}
        with _lock:
            if c.form == "dengue":
                atualizacoes.update(res.atualizacoes)
        msg = f"ok  {res.segundos:5.1f}s  {len(linhas)-1:5d} linhas  {rel}"
    except (ErroTabNet, OSError) as e:
        reg_item = {**base, "status": "erro", "erro": str(e)[:500],
                    "coletado_em": datetime.now().isoformat(timespec="seconds")}
        msg = f"ERRO {rel}: {e}"
    with _lock:
        reg[rel] = reg_item
        gravar_manifesto(reg)
    return msg


def coletar(conjuntos=(1, 2, 3, 4, 5), workers: int = 2, refazer: bool = False, dry_run: bool = False) -> dict:
    """Atualiza o catálogo e executa as consultas pendentes. Retorna o manifesto {arquivo: registro}."""
    a = argparse.Namespace(conjuntos=list(conjuntos), workers=workers, refazer=refazer, dry_run=dry_run)

    cache_pop = DIR_CATALOGO / "catalogo_populacao.json"
    try:
        form, html_form = ler_formulario(DEF_PATH)
        salvar_catalogo(form, html_form)
        form_pop, _ = ler_formulario(DEF_POPULACAO)
        (DIR_CATALOGO / "notas_fonte_populacao.txt").write_text(form_pop.notas + "\n", encoding="utf-8")
        cache_pop.write_text(json.dumps({"def_path": form_pop.def_path, "titulo": form_pop.titulo, "notas": form_pop.notas,
                                         "linhas": [asdict(o) for o in form_pop.linhas],
                                         "colunas": [asdict(o) for o in form_pop.colunas],
                                         "conteudos": [asdict(o) for o in form_pop.conteudos],
                                         "arquivos": [asdict(o) for o in form_pop.arquivos],
                                         "selecoes": {k: [asdict(o) for o in v] for k, v in form_pop.selecoes.items()}},
                                        ensure_ascii=False), encoding="utf-8")
    except requests.RequestException as e:
        # Servidor fora do ar: segue com o catálogo salvo (basta para saber o que já foi baixado)
        print(f"AVISO: TabNet indisponível ({type(e).__name__}); usando o catálogo salvo em {DIR_CATALOGO.relative_to(ROOT)}")
        d = json.loads((DIR_CATALOGO / "catalogo_configuracoes.json").read_text(encoding="utf-8"))
        d.setdefault("def_path", DEF_PATH)
        form = formulario_de_dict(d)
        form_pop = formulario_de_dict(json.loads(cache_pop.read_text(encoding="utf-8")))
    print(f"Catálogo: {len(form.linhas)} linhas, {len(form.colunas)} colunas, {len(form.conteudos)} conteúdo(s), "
          f"{len(form.arquivos)} períodos, {len(form.selecoes)} filtros -> {DIR_CATALOGO.relative_to(ROOT)}")
    forms = {"dengue": form, "populacao": form_pop}

    consultas = [c for c in montar_consultas(form) + montar_consultas_populacao(form_pop) if c.conjunto in a.conjuntos]
    reg = carregar_manifesto()
    pendentes = [c for c in consultas
                 if a.refazer or not c.arquivo.exists()
                 or reg.get(str(c.arquivo.relative_to(ROOT)), {}).get("status") != "ok"]
    print(f"{len(consultas)} consultas nos conjuntos {a.conjuntos}; {len(pendentes)} pendentes")
    if a.dry_run:
        for c in pendentes:
            print(f"  [{c.conjunto}] {c.linha} x {c.coluna} | {len(c.arquivos)} arq | {c.filtros or ''} -> {c.arquivo.relative_to(ROOT)}")
        return reg

    atualizacoes: dict[str, str] = {}
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(executar, c, forms, reg, atualizacoes) for c in pendentes]
        for i, f in enumerate(as_completed(futs), 1):
            print(f"[{i}/{len(pendentes)}] {f.result()}", flush=True)

    if atualizacoes:
        (DIR_CATALOGO / "atualizacao_por_ano.json").write_text(
            json.dumps(dict(sorted(atualizacoes.items())), ensure_ascii=False, indent=2), encoding="utf-8")
    erros = [r for r in reg.values() if r.get("status") != "ok"]
    print(f"Concluído em {(time.time()-t0)/60:.1f} min. {len(reg) - len(erros)} ok, {len(erros)} com erro. Manifesto: {MANIFESTO.relative_to(ROOT)}")
    return reg


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--conjuntos", type=int, nargs="*", default=[1, 2, 3, 4, 5])
    p.add_argument("--workers", type=int, default=2, help="consultas simultâneas (seja gentil com o servidor)")
    p.add_argument("--refazer", action="store_true", help="refaz consultas já baixadas")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    coletar(a.conjuntos, a.workers, a.refazer, a.dry_run)


if __name__ == "__main__":
    main()
