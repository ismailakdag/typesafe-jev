"""Transkript analizi — tarayici eklentisinden gelen cue listesi icin.

Komut satiri araciyla (tools/transkript.py) ayni sorulari ve ayni esikleri
kullanir; oradan ice aktariyoruz ki ikisi zamanla birbirinden ayrilmasin.

Akis:  cue listesi -> parcalar (kod) -> parca basina yargi (Jev) -> derleme (kod)
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, AsyncIterator

from typesafe_sdk import AsyncTypeSafeClient

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK / "tools"))
import transkript as arac  # noqa: E402

CIKTI = arac.CIKTI


# --------------------------------------------------------------------------- #
# Tahmin: cagri yapmadan once ne kadar tutacagini soyler
# --------------------------------------------------------------------------- #
#
# Rakamlar tahminden degil olcumden: 9sa39dk'lik gercek bir videoda 287 parca x
# 26 soru = 577.358 token tuttu. Parca basina 2.012 token; icinden metin ve
# baglam payi cikarilinca soru takimi ~1.291 token yer kapliyor.

SABIT_TOK = 1291      # 26 sorunun kendisi
BAGLAM_TOK = 303      # onceki parcadan tasinan 1500 karakter
TOK_KELIME = 1.11     # ingilizce olcumu
USD_MTOK = 0.042


def tahmin(cue: list[dict], dakika: float) -> dict[str, Any]:
    parcalar = arac.parcala([(c["t"], c["metin"]) for c in cue], dakika)
    kelime = sum(p.kelime for p in parcalar)
    token = int(len(parcalar) * (SABIT_TOK + BAGLAM_TOK) + kelime * TOK_KELIME)
    return {
        "parca": len(parcalar),
        "kelime": kelime,
        "soru": arac.SORU_SAYISI,
        "token": token,
        "usd": round(token * USD_MTOK / 1_000_000, 4),
        "sure_sn": round(cue[-1]["t"] - cue[0]["t"]) if cue else 0,
    }


# --------------------------------------------------------------------------- #
# Analiz: parca basina tek cagri, eszamanli
# --------------------------------------------------------------------------- #

def satir(p: dict[str, Any]) -> str:
    return json.dumps(p, ensure_ascii=False) + "\n"


async def analiz_akisi(
    cue: list[dict],
    dakika: float,
    eszamanli: int,
    video_id: str,
    baslik: str,
) -> AsyncIterator[str]:
    parcalar = arac.parcala([(c["t"], c["metin"]) for c in cue], dakika)
    if not parcalar:
        yield satir({"tip": "hata", "mesaj": "cue listesi boş"})
        return

    q = arac.sorular()
    yield satir({"tip": "basla", "parca": len(parcalar), "soru": arac.SORU_SAYISI,
                 "tahmin": tahmin(cue, dakika)})

    kilit = asyncio.Semaphore(eszamanli)
    sonuc: dict[int, dict] = {}
    toplam_tok = 0
    hata = 0
    t0 = time.perf_counter()
    kuyruk: asyncio.Queue[str | None] = asyncio.Queue()

    async with AsyncTypeSafeClient() as client:
        async def calis(p: arac.Parca) -> None:
            nonlocal toplam_tok, hata
            onceki = parcalar[p.no - 1].metin[-1500:] if p.no else "(this is the first passage)"
            async with kilit:
                try:
                    r = await client.system_one({"bolum": p.metin, "onceki_bolum": onceki}, q)
                except Exception as e:  # tek parca dusmesi analizi bitirmesin
                    hata += 1
                    await kuyruk.put(satir({"tip": "parca_hata", "no": p.no, "mesaj": str(e)[:200]}))
                    return
            toplam_tok += r.usage.input_tokens or 0
            sonuc[p.no] = {
                "no": p.no, "bas": p.bas, "son": p.son, "kelime": p.kelime,
                "metin": p.metin,
                "nouls": {k: round(v.noul, 3) for k, v in r.nouls.items()},
                "choices": {k: {"secim": v.choice, "guven": round(v.confidence, 3)}
                            for k, v in r.choices.items()},
                "scores": {k: {"skor": round(v.score, 2), "guven": round(v.confidence, 3)}
                           for k, v in r.scores.items()},
                "token": r.usage.input_tokens,
            }
            await kuyruk.put(satir({
                "tip": "parca", "no": p.no, "bitti": len(sonuc), "toplam": len(parcalar),
                "token": toplam_tok, "usd": round(toplam_tok * USD_MTOK / 1_000_000, 4),
            }))

        gorev = asyncio.create_task(_hepsi(calis, parcalar, kuyruk))
        while True:
            s = await kuyruk.get()
            if s is None:
                break
            yield s
        await gorev

    gecen = time.perf_counter() - t0
    P = [sonuc[k] for k in sorted(sonuc)]
    if not P:
        yield satir({"tip": "hata", "mesaj": "hiçbir parça analiz edilemedi"})
        return

    # Ham yargilar diske: derle/disa komutlari bunu okuyabilsin.
    ad = f"yt-{video_id}" if video_id else "yt-bilinmeyen"
    yol = CIKTI / f"{ad}.json"
    yol.write_text(json.dumps(
        {"kaynak": baslik or ad, "video_id": video_id, "dakika": dakika,
         "soru_sayisi": arac.SORU_SAYISI, "parcalar": P},
        ensure_ascii=False), encoding="utf-8")

    yield satir({
        "tip": "bitti",
        "ozet": {
            "parca": len(P), "hata": hata, "saniye": round(gecen, 1),
            "token": toplam_tok, "usd": round(toplam_tok * USD_MTOK / 1_000_000, 4),
            "dosya": str(yol),
        },
        "sonuc": derle(P),
    })


async def _hepsi(calis, parcalar, kuyruk) -> None:
    try:
        await asyncio.gather(*(calis(p) for p in parcalar))
    finally:
        await kuyruk.put(None)


# --------------------------------------------------------------------------- #
# Derleme: arayuzun gosterecegi bicim
# --------------------------------------------------------------------------- #

def _onizleme(p: dict, kelime: int = 22) -> str:
    return " ".join(p["metin"].split()[:kelime])


def derle(P: list[dict]) -> dict[str, Any]:
    """Esikler tools/transkript.py'de; burada yalnizca sunuma ceviriyoruz."""
    d = arac.derle_veri(P)
    s = lambda p, a: p["scores"].get(a, {}).get("skor", 0)  # noqa: E731

    def liste(kayitlar: list[dict], limit: int = 60) -> list[dict]:
        sirali = sorted(kayitlar, key=lambda x: -s(x, "ogretici_deger"))[:limit]
        return [{"t": round(p["bas"], 1), "zaman": arac.zaman(p["bas"]),
                 "puan": round(s(p, "ogretici_deger"), 1),
                 "metin": _onizleme(p)} for p in sirali]

    bolumler = [{
        "no": i, "t": round(b["bas"], 1), "zaman": arac.zaman(b["bas"]),
        "dakika": round((b["son"] - b["bas"]) / 60),
        "turler": b["turler"][:3], "yontem": b["yontem_var"],
        "puan": round(b["ogretici"], 1),
    } for i, b in enumerate(d["bolumler"], 1)]

    return {
        "bolumler": bolumler,
        "yontemler": liste(d["yontemler"]),
        "alistirmalar": liste(d["alistirmalar"]),
        "ornekler": liste(d["ornekler"]),
        "arastirmalar": liste(d["arastirmalar"]),
        "kesme": {
            "toplam_sn": round(d["toplam"]),
            "tutulan_sn": round(d["tutulan"]),
            "yuzde": round(100 * d["tutulan"] / d["toplam"]) if d["toplam"] else 0,
            "aralik": [{"bas": round(a["bas"], 1), "son": round(a["son"], 1)}
                       for a in d["araliklar"]],
        },
    }
