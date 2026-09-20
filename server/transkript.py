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
# Sorularin kendisi: arayuzde gosterilebilsin diye
# --------------------------------------------------------------------------- #
#
# "Neye gore karar verdi" sorusunun yarisi bu: hangi soru soruluyor. Diger
# yarisi ESIKLER: cevaplar hangi kurala carpinca listeye giriyor.

GRUPLAR: list[tuple[str, str, list[str]]] = [
    ("icerik", "Bu parça ne anlatıyor?",
     ["yontem", "adim_listesi", "ilke", "tanim", "ornek_hikaye", "arastirma",
      "alistirma", "soru_sorusu", "alinti"]),
    ("deger", "Bu parça yeni bir şey katıyor mu?",
     ["yeni_icerik", "tekrar", "ozet", "gecis", "idari", "tanitim", "dolgu"]),
    ("yapi", "Burada bir sınır var mı?",
     ["konu_degisti", "bolum_acilis", "bolum_kapanis"]),
    ("kesme", "Buradan kesilse ne olur?",
     ["yarim_baslangic", "yarim_bitis", "onceki_gerekli"]),
    ("siniflandirma", "Tek kelimeyle ne yapıyor?", ["bolum_turu"]),
    ("puan", "Ne kadar değerli? (0–3)",
     ["bilgi_yogunlugu", "ogretici_deger", "kendi_basina"]),
]

ESIKLER: dict[str, str] = {
    "bolumler": "Yeni bölüm sınırı: konu_degisti > 0,85 VEYA bolum_acilis > 0,80. "
                "Tek parçalık bölümler bir öncekine katılır. "
                "(Eşikler ölçümle seçildi: 24 gerçek bölüme karşı %92 duyarlılık, "
                "%81 kesinlik. 0,60 eşiği %49 kesinlikte kalıyordu.)",
    "yontemler": "yontem > 0,85 VE ogretici_deger ≥ 2,3",
    "alistirmalar": "alistirma > 0,65",
    "ornekler": "ornek_hikaye > 0,70 VE ogretici_deger ≥ 2,0",
    "arastirmalar": "arastirma > 0,65",
    "kesme": "Atılır: idari > 0,60 VEYA tanitim > 0,60 — ya da "
             "(bilgi_yogunlugu < 1,2 VE ogretici_deger < 1,2) ile birlikte "
             "tekrar/gecis/dolgu > 0,50. Kalan parçalar bitişikse tek aralık olur.",
}


def soru_dokumu() -> dict[str, Any]:
    """26 sorunun kendisini serilestirir: ne soruldugu arayuzde okunabilsin."""
    q = arac.sorular()

    def tek(ad: str) -> dict[str, Any]:
        o = q[ad]
        tur = type(o).__name__
        d: dict[str, Any] = {"ad": ad, "tur": tur, "soru": o.instructions}
        if tur == "Noul" and o.criteria:
            d["evet"] = o.criteria.get("true")
            d["hayir"] = o.criteria.get("false")
        elif tur == "Choice":
            d["secenekler"] = [{"ad": k, "aciklama": v} for k, v in (o.criteria or {}).items()]
        elif tur == "Score":
            d["seviyeler"] = list(o.criteria or [])
        return d

    return {
        "sayi": arac.SORU_SAYISI,
        "gruplar": [{"ad": ad, "baslik": baslik, "sorular": [tek(x) for x in adlar]}
                    for ad, baslik, adlar in GRUPLAR],
        "esikler": ESIKLER,
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
        "sonuc": derle(P, cue),
    })


async def _hepsi(calis, parcalar, kuyruk) -> None:
    try:
        await asyncio.gather(*(calis(p) for p in parcalar))
    finally:
        await kuyruk.put(None)


# --------------------------------------------------------------------------- #
# Derleme: arayuzun gosterecegi bicim
# --------------------------------------------------------------------------- #

def _kayit(p: dict, s) -> dict[str, Any]:
    """Bir parcanin sunum kaydi. METIN TAM: disa aktarmada kirpilmis metin
    istemiyoruz, arayuz kirpmayi kendi yapiyor (CSS)."""
    return {
        "no": p["no"],
        "t": round(p["bas"], 1),
        "son": round(p["son"], 1),
        "zaman": arac.zaman(p["bas"]),
        "puan": round(s(p, "ogretici_deger"), 1),
        "yogunluk": round(s(p, "bilgi_yogunlugu"), 1),
        "kelime": p["kelime"],
        "metin": p["metin"],
    }


def _kapsam(P: list[dict], cue: list[dict] | None) -> dict[str, Any]:
    """Bastan ya da ortadan bir sey dusmus mu — tahmin degil olcum.

    "Basi kaciriyor" suphesini kontrol edilebilir kilmak icin: transkript kacta
    basliyor, arada kac saniyelik sessizlik var, ilk bolum ne kadar uzun.
    """
    d: dict[str, Any] = {"ilk_cue": round(P[0]["bas"], 1), "son_cue": round(P[-1]["son"], 1)}
    if cue:
        t = [c["t"] for c in cue]
        bosluk = [(round(t[i] - t[i - 1], 1), round(t[i - 1], 1))
                  for i in range(1, len(t)) if t[i] - t[i - 1] > 20]
        d["bosluk"] = sorted(bosluk, reverse=True)[:5]
        d["bosluk_sayisi"] = len(bosluk)
    return d


def derle(P: list[dict], cue: list[dict] | None = None) -> dict[str, Any]:
    """Esikler tools/transkript.py'de; burada yalnizca sunuma ceviriyoruz."""
    d = arac.derle_veri(P)
    n = lambda p, a: p["nouls"].get(a, 0)                    # noqa: E731
    s = lambda p, a: p["scores"].get(a, {}).get("skor", 0)   # noqa: E731

    # Siralama puana gore, ama LIMIT YOK: disa aktarirken tamami lazim.
    def liste(kayitlar: list[dict]) -> list[dict]:
        return [_kayit(p, s) for p in sorted(kayitlar, key=lambda x: -s(x, "ogretici_deger"))]

    bolumler = []
    for i, b in enumerate(d["bolumler"], 1):
        icinde = [p for p in P if b["bas"] <= p["bas"] <= b["son"]]
        bolumler.append({
            "no": i, "t": round(b["bas"], 1), "son": round(b["son"], 1),
            "zaman": arac.zaman(b["bas"]),
            "dakika": round((b["son"] - b["bas"]) / 60),
            "turler": b["turler"][:3], "yontem": b["yontem_var"],
            "puan": round(b["ogretici"], 1),
            "parca_no": [p["no"] for p in icinde],
            "metin": " ".join(p["metin"] for p in icinde),
        })

    # Atilanlar da gorunsun: neyin elendigi gizli kalmasin, kullanici
    # kendi gozuyle bakip esiklerin dogru olup olmadigina karar verebilsin.
    tutulan = {p["no"] for p in P if not arac.atilir(p)}
    atilan = [{**_kayit(p, s), "neden": _atma_nedeni(p, n, s)}
              for p in P if p["no"] not in tutulan]

    return {
        "parca_sayisi": len(P),
        "bolumler": bolumler,
        "yontemler": liste(d["yontemler"]),
        "alistirmalar": liste(d["alistirmalar"]),
        "ornekler": liste(d["ornekler"]),
        "arastirmalar": liste(d["arastirmalar"]),
        "atilan": atilan,
        "tumu": [_kayit(p, s) for p in P],
        "kesme": {
            "toplam_sn": round(d["toplam"]),
            "tutulan_sn": round(d["tutulan"]),
            "yuzde": round(100 * d["tutulan"] / d["toplam"]) if d["toplam"] else 0,
            "aralik": [{"bas": round(a["bas"], 1), "son": round(a["son"], 1)}
                       for a in d["araliklar"]],
            "tutulan_no": sorted(tutulan),
        },
        "kapsam": _kapsam(P, cue),
        "esikler": ESIKLER,
    }


# Kararin kendisi arac.atilir(); burada yalnizca NEDENINI yaziya dokuyoruz.

def _atma_nedeni(p: dict, n, s) -> str:
    if n(p, "idari") > 0.6:
        return f"idari ({n(p, 'idari'):.2f})"
    if n(p, "tanitim") > 0.6:
        return f"tanıtım ({n(p, 'tanitim'):.2f})"
    hangi = max(("tekrar", "gecis", "dolgu"), key=lambda a: n(p, a))
    ad = {"tekrar": "tekrar", "gecis": "geçiş", "dolgu": "dolgu"}[hangi]
    return (f"düşük yoğunluk ({s(p, 'bilgi_yogunlugu'):.1f}/3, "
            f"öğretici {s(p, 'ogretici_deger'):.1f}/3) + {ad} ({n(p, hangi):.2f})")
