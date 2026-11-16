"""
Estilo único dos gráficos (Matplotlib).

Paleta categórica validada para daltonismo (ordem fixa, nunca reciclada), rampa sequencial
de um só tom (azul) e cores de status reservadas para níveis de alerta.
Regras seguidas: um eixo y por gráfico (nada de eixo duplo), marcas finas, grade discreta,
legenda sempre que houver 2+ séries e rótulos diretos seletivos.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRADE = "#e4e3df"

# Ordem fixa: azul, laranja, água, amarelo, magenta, verde, violeta, vermelho
CATEGORICA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
NEUTRO = "#a8a7a2"
# Status (só para níveis de alerta — sempre acompanhados de rótulo)
STATUS = {"baixo": "#0ca30c", "moderado": "#fab219", "alto": "#ec835a", "muito alto": "#d03b3b"}

AZUL, LARANJA, AGUA, AMARELO = CATEGORICA[:4]


def aplicar_estilo() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
        "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.titlepad": 12, "axes.labelsize": 10, "axes.labelcolor": TEXTO_2,
        "text.color": TEXTO, "axes.edgecolor": GRADE, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRADE, "grid.linewidth": 0.8,
        "axes.axisbelow": True, "axes.prop_cycle": mpl.cycler(color=CATEGORICA),
        "lines.linewidth": 2.0, "lines.markersize": 6,
        "legend.frameon": False, "legend.fontsize": 9,
        "patch.linewidth": 0,
    })


def milhar(ax, eixo: str = "y", casas: int = 0) -> None:
    """Formata números no padrão brasileiro (1.234.567)."""
    fmt = mticker.FuncFormatter(lambda v, _: f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", "."))
    (ax.yaxis if eixo == "y" else ax.xaxis).set_major_formatter(fmt)


def fmt_br(v: float, casas: int = 0) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def subtitulo(ax, texto: str, espaco: int = 26) -> None:
    """Linha de apoio sob o título (chamar depois de ax.set_title)."""
    loc = mpl.rcParams["axes.titlelocation"]
    ax.set_title(ax.get_title(loc=loc), pad=espaco, loc=loc)
    ax.text(0, 1.02, texto, transform=ax.transAxes, fontsize=9, color=TEXTO_2, va="bottom")


def legenda_topo(ax, ncols: int | None = None, **kw) -> None:
    """Legenda em uma linha entre o título e a área do gráfico (não cobre dados)."""
    h, l = ax.get_legend_handles_labels()
    ax.legend(h, l, loc="lower left", bbox_to_anchor=(0, 1.0), ncols=ncols or len(l),
              borderaxespad=0.2, handlelength=1.6, columnspacing=1.4, **kw)


def fonte(fig, texto: str) -> None:
    fig.text(0.01, -0.02, texto, fontsize=8, color=TEXTO_2, ha="left", va="top")


def salvar(fig, nome: str, pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{nome}.png"
    fig.savefig(caminho)
    return caminho
