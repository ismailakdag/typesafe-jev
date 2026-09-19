"""Jev'e ne kadar hazirlik vermek gerekiyor?

Ayni ilan, ayni sorular, uc farkli hazirlik seviyesi. Amac: "kriterleri yazmasak
ne kaybederiz" sorusunu tahminle degil olcumle cevaplamak.

  1. CIPLAK       state = sadece ilan metni (duz yazi)
                  sorular = sadece instructions, criteria yok
  2. YAPILANDIRIL state = baslik + alanlar + aciklama + profil (+ hasar semasi)
                  sorular = sadece instructions, criteria yok
  3. TAM          ayni state + her soruda criteria (projenin bugunku hali)

Calistir:  uv run python tools/deney_kriter.py
"""

from __future__ import annotations

import asyncio
import glob
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Score

from server import analyzer

load_dotenv()

# Her seviyede sorulan AYNI dort yargi. Ciplak surumde yalnizca instructions var.
YONERGELER = {
    "kiracili": "Bu ilandaki daire veya araç kiracılı mı, yoksa boş mu teslim edilecek?",
    "celiski": "İlandaki bilgiler birbiriyle çelişiyor mu?",
    "satici": "Bu ilanı kim yazmış?",
    "uygunluk": "İlan, alıcının aradığı şeye ne kadar uyuyor?",
}

# Ayni yargilarin kriterli hali.
TAM = {
    "kiracili": Noul(
        instructions=YONERGELER["kiracili"],
        criteria={
            "true": "Metin kiracıdan, kira kontratından ya da kiracılı teslimden söz ediyor",
            "false": "Metin boş/sıfır olduğunu söylüyor ya da konuya hiç değinmiyor",
        },
    ),
    "celiski": Noul(
        instructions=YONERGELER["celiski"],
        criteria={
            "true": "`yapilandirilmis_alanlar` ile `aciklama` en az bir konuda birbirini tutmuyor",
            "false": "İkisi tutarlı ya da açıklama o konulara değinmiyor",
        },
    ),
    "satici": Choice(
        instructions=YONERGELER["satici"] + " Etiketi değil, metnin dilini esas al.",
        criteria={
            "sahibi": "Malı kendi kullanan kişinin kendi ağzından anlatımı",
            "kurumsal": "Emlak ofisi, galeri veya kurumsal pazarlama dili",
            "belirsiz": "Metinden anlaşılmıyor",
        },
    ),
    "uygunluk": Score(
        instructions=YONERGELER["uygunluk"] + " Yalnızca `alici_profili` alanına dayan.",
        criteria=[
            "Alıcının önceliklerine açıkça aykırı",
            "Zayıf uyum: birkaç önceliği karşılıyor",
            "İyi uyum: önceliklerin çoğunu karşılıyor",
            "Tarif edilen kullanıma birebir uyuyor",
        ],
    ),
}

# Ciplak: ayni sorular ama criteria yok. Choice'ta secenek adlari zorunlu,
# o yuzden yalnizca etiketler verilip aciklamalari bos birakiliyor.
CIPLAK = {
    "kiracili": Noul(instructions=YONERGELER["kiracili"]),
    "celiski": Noul(instructions=YONERGELER["celiski"]),
    "satici": Choice(instructions=YONERGELER["satici"],
                     criteria={"sahibi": None, "kurumsal": None, "belirsiz": None}),
    "uygunluk": Score(instructions=YONERGELER["uygunluk"],
                      criteria=["çok kötü", "kötü", "iyi", "çok iyi"]),
}

PROFIL = analyzer.Kriterler(
    profil="Günlük kullanım, uzun vadeli. İzmir Çiğli çevresi.",
    oncelikler="Ulaşım kolaylığı, düşük işletme maliyeti, taşınmaya hazır olması",
    kirmizi_cizgiler="Kiracılı teslim, bilgilerin çelişkili olması",
)


def ilan_yukle(dosya: str) -> dict:
    d = json.loads(Path(dosya).read_text(encoding="utf-8"))
    return d["captures"][-1]


async def kos(client, ad: str, state, sorular) -> dict:
    t0 = time.perf_counter()
    cevap = await client.system_one(state, sorular)
    ms = (time.perf_counter() - t0) * 1000
    return {
        "ad": ad, "ms": round(ms),
        "token": cevap.usage.input_tokens or 0,
        "kiracili": round(cevap.nouls["kiracili"].noul, 3),
        "celiski": round(cevap.nouls["celiski"].noul, 3),
        "satici": cevap.choices["satici"].choice,
        "satici_guven": round(cevap.choices["satici"].confidence, 3),
        "uygunluk": round(cevap.scores["uygunluk"].score, 2),
        "uygunluk_guven": round(cevap.scores["uygunluk"].confidence, 3),
    }


async def main() -> None:
    dosyalar = sorted(glob.glob("data/ilanlar/*.json"))
    secim = []
    for f in dosyalar:
        k = ilan_yukle(f)
        secim.append((k.get("kategori", "emlak"), k))
    # Bir emlak bir vasita sec
    ornekler = []
    for kat in ("emlak", "vasita"):
        for k_kat, k in secim:
            if k_kat == kat:
                ornekler.append((kat, k))
                break

    async with AsyncTypeSafeClient() as client:
        for kat, ilan in ornekler:
            tam_state = analyzer.durum(ilan, PROFIL)
            ciplak_state = (ilan.get("aciklama") or "")[:6000]

            print("=" * 78)
            print(f"{kat.upper()}  ·  {(ilan.get('baslik') or '')[:60]}")
            print("=" * 78)

            sonuclar = [
                await kos(client, "1 çıplak      ", ciplak_state, CIPLAK),
                await kos(client, "2 yapılandır. ", tam_state, CIPLAK),
                await kos(client, "3 tam         ", tam_state, TAM),
            ]

            print(f"{'seviye':15} {'kiracılı':>9} {'çelişki':>8} {'satıcı':>12} {'güven':>7} "
                  f"{'uygunluk':>9} {'güven':>7} {'token':>6} {'ms':>5}")
            print("-" * 96)
            for s in sonuclar:
                print(f"{s['ad']:15} {s['kiracili']:9.3f} {s['celiski']:8.3f} "
                      f"{s['satici']:>12} {s['satici_guven']:7.2f} "
                      f"{s['uygunluk']:9.2f} {s['uygunluk_guven']:7.2f} "
                      f"{s['token']:6} {s['ms']:5}")
            print()


if __name__ == "__main__":
    asyncio.run(main())
