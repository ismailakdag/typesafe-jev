"""Vasita hasar kapisinin dogrulugu.

Bu kapi bilerek KODDA: modele "ilan semayla celisiyor mu" diye sorulunca cevap
surekli 0.5 civarinda kaliyor, cunku baslik "hasar kaydi yok" derken (tramer
kaydi gercekten yok) aciklama degisen parcalari kabul edebiliyor. Model hakli
olarak ikircikli kaliyor ve her ilan "emin degil" diye insana dusuyordu.

Sema zaten yapilandirilmis veri; celiskiyi kod kesin kurar.

Calistir:  uv run python tools/test_hasar_kapisi.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import analyzer  # noqa: E402


def sahte_cevap(beyan: str, guven: float) -> NS:
    """Yalnizca kapinin ihtiyac duydugu alanlari tasiyan asgari bir cevap."""
    return NS(
        nouls={
            "agir_hasar_imasi": NS(noul=0.02),
            "ticari_kullanim": NS(noul=0.05),
            "metin_yetersiz": NS(noul=0.10),
        },
        choices={
            "hasar_beyani": NS(
                choice=beyan, confidence=guven,
                probabilities={beyan: guven, "kismi_kabul": 1 - guven},
            ),
            "satici_dili": NS(
                choice="galeri", confidence=0.95,
                probabilities={"galeri": 0.95, "belirsiz": 0.05},
            ),
        },
        scores={
            ad: NS(score=3.0, confidence=0.9, probabilities={0: 0.0, 1: 0.0, 2: 0.1, 3: 0.9})
            for ad in analyzer.AGIRLIKLAR_VASITA
        },
    )


SENARYOLAR = [
    # (aciklama, beyan, guven, orijinal_disi, kapi acilmali mi)
    ("metin hasarsız diyor, şemada 8 boyalı panel", "tamamen_hasarsiz", 0.94, 8, True),
    ("metin hasarsız diyor, şema tertemiz", "tamamen_hasarsiz", 0.94, 0, False),
    ("metin kısmi kabul ediyor, şemada 8 boyalı", "kismi_kabul", 0.94, 8, False),
    ("metin hasarsız diyor ama model emin değil", "tamamen_hasarsiz", 0.45, 8, False),
    ("metin hasar durumuna değinmiyor", "belirsiz", 0.80, 8, False),
]


def main() -> None:
    hata = 0
    for ad, beyan, guven, orijinal_disi, beklenen in SENARYOLAR:
        karar = analyzer.karar_ver(
            sahte_cevap(beyan, guven), "vasita", None,
            {"hasar": {"orijinal_disi": orijinal_disi, "ozet": f"{orijinal_disi} panel orijinal değil"}},
        )
        kapi = next(g for g in karar.kapilar if g["ad"] == "hasar_beyani")
        oldu = kapi["tetikledi"]
        isaret = "ok  " if oldu == beklenen else "HATA"
        if oldu != beklenen:
            hata += 1
        print(f"{isaret} {ad:46} kapı={'açık' if oldu else 'kapalı':6} sonuç={karar.sonuc}")

    print()
    print("tüm senaryolar geçti" if not hata else f"{hata} senaryo başarısız")
    raise SystemExit(1 if hata else 0)


if __name__ == "__main__":
    main()
