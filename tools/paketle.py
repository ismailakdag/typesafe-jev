"""Paylasilabilir zip uretir.

Disarida birakilanlar bilerek secildi:
  - .env            : API anahtari. Asla paketlenmez.
  - data/           : kendi arsivin, kullanim defterin, profilin, ek sorularin.
                      Karsi taraf temiz baslasin.
  - data/ornek/     : kayitli sahibinden sayfalari. Baskasinin icerigini
                      yeniden dagitmanin alemi yok; gelistirme icin yerel kalsin.
  - .venv, node_modules, .git, __pycache__ : uretilen/indirilen seyler.

Calistir:  uv run python tools/paketle.py
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / f"typesafe-jev-{date.today().isoformat()}.zip"

# Pakete girecekler
DOSYALAR = [
    "KURULUM.md",
    "README.md",
    "basla.cmd",
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    ".gitignore",
]
KLASORLER = ["extension", "server", "tools"]

# Klasorlerin icinde de atlanacaklar
ATLA_PARCA = {"__pycache__", ".venv", "node_modules", ".git"}
ATLA_UZANTI = {".pyc", ".pyo", ".log"}


def girer_mi(p: Path) -> bool:
    if any(parca in ATLA_PARCA for parca in p.parts):
        return False
    if p.suffix in ATLA_UZANTI:
        return False
    if p.name == ".env":
        return False
    return True


def main() -> None:
    if HEDEF.exists():
        HEDEF.unlink()

    eklenen: list[str] = []
    with zipfile.ZipFile(HEDEF, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for ad in DOSYALAR:
            yol = KOK / ad
            if yol.exists():
                z.write(yol, f"typesafe-jev/{ad}")
                eklenen.append(ad)

        for klasor in KLASORLER:
            for yol in sorted((KOK / klasor).rglob("*")):
                if not yol.is_file() or not girer_mi(yol.relative_to(KOK)):
                    continue
                goreli = yol.relative_to(KOK).as_posix()
                z.write(yol, f"typesafe-jev/{goreli}")
                eklenen.append(goreli)

        # Bos data klasoru: uygulama ilk calistiginda kendisi doldurur.
        z.writestr("typesafe-jev/data/.gitkeep", "")

    # Guvenlik kontrolu: sizmis bir sir var mi?
    with zipfile.ZipFile(HEDEF) as z:
        adlar = z.namelist()
    sizinti = [a for a in adlar if a.endswith(".env") or "/data/ilanlar/" in a or a.endswith("kullanim.json")]

    print(f"{HEDEF.name}  —  {HEDEF.stat().st_size / 1024:.0f} KB, {len(adlar)} dosya")
    print(f"konum: {HEDEF}")
    print()
    for a in eklenen:
        print("  " + a)
    print()
    print("sizinti kontrolu:", "TEMIZ" if not sizinti else f"DIKKAT -> {sizinti}")


if __name__ == "__main__":
    main()
