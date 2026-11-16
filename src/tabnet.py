"""
Cliente mínimo para o TabNet do DATASUS.

O TabNet é um formulário HTML (deftohtm.exe) que envia um POST para tabcgi.exe.
A resposta no formato "prn" (colunas separadas por ";") vem dentro de um bloco <PRE>.
O servidor trabalha em ISO-8859-1 (latin1), por isso o corpo do POST é codificado em latin1.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus

import requests

TABNET_HOST = "https://tabnet.datasus.gov.br"
NAO_ATIVA = "--Não-Ativa--"
TODAS = "TODAS_AS_CATEGORIAS__"

_RE_SELECT = re.compile(r'<SELECT[^>]*NAME="([^"]+)"[^>]*>(.*?)</SELECT>', re.S | re.I)
_RE_OPTION = re.compile(r'<OPTION\s+VALUE="([^"]*)"\s*(SELECTED)?\s*>([^<\r\n]*)', re.I)
_RE_PRE = re.compile(r"<PRE>(.*?)</PRE>", re.S | re.I)
_RE_ATUALIZACAO = re.compile(r"Dados de (\d{4}) atualizados em ([^.<]+)", re.I)


@dataclass
class Opcao:
    valor: str
    rotulo: str
    selecionada: bool = False


@dataclass
class FormularioTabNet:
    """Todas as configurações possíveis de uma tabulação TabNet."""

    def_path: str  # ex.: "sinannet/cnv/denguebbr.def"
    titulo: str
    linhas: list[Opcao]
    colunas: list[Opcao]
    conteudos: list[Opcao]
    arquivos: list[Opcao]
    selecoes: dict[str, list[Opcao]] = field(default_factory=dict)
    notas: str = ""

    @property
    def url_form(self) -> str:
        return f"{TABNET_HOST}/cgi/deftohtm.exe?{self.def_path}"

    @property
    def url_tab(self) -> str:
        return f"{TABNET_HOST}/cgi/tabcgi.exe?{self.def_path}"


def _limpa(txt: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(txt)).strip()


def formulario_de_dict(d: dict) -> FormularioTabNet:
    """Reconstrói o formulário a partir do catálogo salvo (uso offline)."""
    op = lambda lst: [Opcao(**o) for o in lst]  # noqa: E731
    return FormularioTabNet(
        def_path=d["def_path"], titulo=d.get("titulo", ""), linhas=op(d["linhas"]), colunas=op(d["colunas"]),
        conteudos=op(d["conteudos"]), arquivos=op(d["arquivos"]),
        selecoes={k: op(v) for k, v in d["selecoes"].items()}, notas=d.get("notas", ""),
    )


def ler_formulario(def_path: str, session: requests.Session | None = None, tentativas: int = 3) -> tuple[FormularioTabNet, str]:
    """Baixa e interpreta o formulário. Retorna (formulário, html bruto)."""
    s = session or requests.Session()
    for t in range(1, tentativas + 1):
        try:
            r = s.get(f"{TABNET_HOST}/cgi/deftohtm.exe?{def_path}", timeout=90)
            r.raise_for_status()
            break
        except requests.RequestException:
            if t == tentativas:
                raise
            time.sleep(10 * t)
    bruto = r.content.decode("latin1")

    selects: dict[str, list[Opcao]] = {}
    for nome, corpo in _RE_SELECT.findall(bruto):
        selects[nome] = [Opcao(v, _limpa(t), bool(sel)) for v, sel, t in _RE_OPTION.findall(corpo)]

    titulo_m = re.search(r'<H2 class="Nivel0">(.*?)</H2>', bruto, re.S | re.I)
    notas_m = re.search(r'<div class="rodape_htm">(.*?)</div>', bruto, re.S | re.I)
    form = FormularioTabNet(
        def_path=def_path,
        titulo=_limpa(re.sub(r"<[^>]+>", "", titulo_m.group(1))) if titulo_m else def_path,
        linhas=selects.pop("Linha"),
        colunas=selects.pop("Coluna"),
        conteudos=[o for o in selects.pop("Incremento") if o.valor],
        arquivos=selects.pop("Arquivos"),
        selecoes={k: v for k, v in selects.items() if k.startswith("S")},
        notas=_limpa(re.sub(r"<[^>]+>", "\n", notas_m.group(1))) if notas_m else "",
    )
    return form, bruto


@dataclass
class ResultadoTabNet:
    csv: str  # conteúdo ";"-separado, já em UTF-8 e sem entidades HTML
    html: str  # resposta bruta completa
    segundos: float
    atualizacoes: dict[str, str]  # ano -> "dd/mm/aaaa ..."


class ErroTabNet(RuntimeError):
    pass


def _enc(k: str, v: str) -> str:
    return quote_plus(k.encode("latin1")) + "=" + quote_plus(v.encode("latin1"))


def consultar(
    form: FormularioTabNet,
    linha: str,
    coluna: str = NAO_ATIVA,
    arquivos: list[str] | None = None,
    conteudo: str | None = None,
    filtros: dict[str, list[str]] | None = None,
    exibir_zeradas: bool = False,
    session: requests.Session | None = None,
    timeout: int = 900,
    tentativas: int = 4,
) -> ResultadoTabNet:
    """Executa uma tabulação e devolve o CSV (separador ';')."""
    s = session or requests.Session()
    arquivos = arquivos or [form.arquivos[0].valor]
    conteudo = conteudo or form.conteudos[0].valor
    filtros = filtros or {}

    partes = [_enc("Linha", linha), _enc("Coluna", coluna), _enc("Incremento", conteudo)]
    partes += [_enc("Arquivos", a) for a in arquivos]
    for nome in form.selecoes:
        for v in filtros.get(nome, [TODAS]):
            partes.append(_enc(nome, v))
    if exibir_zeradas:
        partes.append(_enc("zeradas", "exibirlz"))
    partes += [_enc("formato", "prn"), _enc("mostre", "Mostra")]
    corpo = "&".join(partes)

    ultimo_erro: Exception | None = None
    for t in range(1, tentativas + 1):
        try:
            t0 = time.time()
            r = s.post(
                form.url_tab,
                data=corpo,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            )
            r.raise_for_status()
            bruto = r.content.decode("latin1")
            m = _RE_PRE.search(bruto)
            if not m:
                msg = _limpa(re.sub(r"<[^>]+>", " ", bruto))[:300]
                raise ErroTabNet(f"resposta sem tabela: {msg}")
            linhas = [l for l in html.unescape(m.group(1)).strip().splitlines() if l.strip() and l.strip() != "&"]
            return ResultadoTabNet(
                csv="\n".join(linhas) + "\n",
                html=bruto,
                segundos=time.time() - t0,
                atualizacoes=dict(_RE_ATUALIZACAO.findall(bruto)),
            )
        except (requests.RequestException, ErroTabNet) as e:
            ultimo_erro = e
            time.sleep(15 * t)
    raise ErroTabNet(f"falhou após {tentativas} tentativas: {ultimo_erro}")
