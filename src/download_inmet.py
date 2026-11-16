"""
Download dos dados históricos anuais do INMET (estações automáticas).

Fonte: https://portal.inmet.gov.br/dadoshistoricos
Cada ano é um .zip com um CSV por estação (dados horários).

Uso:
    python src/download_inmet.py                 # 2014 a 2026 (mesmo período do SINAN/DATASUS)
    python src/download_inmet.py --inicio 2018 --fim 2024
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

from config import ANO_FIM, ANO_INICIO, RAW_INMET

BASE_URL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"
DEST = RAW_INMET / "zip"
HEADERS = {
    # O portal derruba conexões sem User-Agent de navegador.
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}


def tamanho_remoto(url: str) -> int | None:
    r = requests.head(url, headers=HEADERS, timeout=60, allow_redirects=True)
    r.raise_for_status()
    cl = r.headers.get("Content-Length")
    return int(cl) if cl else None


def baixar_ano(ano: int, tentativas: int = 4) -> Path:
    url = BASE_URL.format(ano=ano)
    destino = DEST / f"{ano}.zip"
    esperado = tamanho_remoto(url)

    if destino.exists() and esperado and destino.stat().st_size == esperado:
        print(f"[{ano}] já existe ({esperado / 1e6:.1f} MB) — pulando")
        return destino

    for t in range(1, tentativas + 1):
        try:
            tmp = destino.with_suffix(".zip.part")
            with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            if esperado and tmp.stat().st_size != esperado:
                raise IOError(f"tamanho divergente: {tmp.stat().st_size} != {esperado}")
            tmp.replace(destino)
            print(f"[{ano}] ok ({destino.stat().st_size / 1e6:.1f} MB)")
            return destino
        except Exception as e:  # noqa: BLE001
            espera = 10 * t
            print(f"[{ano}] falha na tentativa {t}/{tentativas}: {e} — nova tentativa em {espera}s")
            time.sleep(espera)
    raise RuntimeError(f"Não foi possível baixar {url}")


def baixar(inicio: int = ANO_INICIO, fim: int = ANO_FIM) -> list[Path]:
    DEST.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for ano in range(inicio, fim + 1):
        arquivos.append(baixar_ano(ano))
        time.sleep(1)  # respeitar o servidor
    return arquivos


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inicio", type=int, default=ANO_INICIO)
    p.add_argument("--fim", type=int, default=ANO_FIM)
    a = p.parse_args()

    baixar(a.inicio, a.fim)


if __name__ == "__main__":
    main()
