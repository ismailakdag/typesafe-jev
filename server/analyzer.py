"""Kod filtresi + Jev yargilari + agirlikli skor.

Is bolumu kasitli:
  - Sayisal ve kesin olan her sey KODDA (fiyat, alan, aidat, mesafe). Jev sayilarda
    zayif ve bu filtreler zaten kesin; modele sormak hem yanlis hem gereksiz maliyet.
  - Jev'e yalnizca metinden cikan yargilar sorulur: celiski, abarti, satici dili,
    profile uygunluk. Bunlari kod yapamaz.
  - Nihai karar yine kodda: kirmizi bayraklar ayri kosul, tercihler agirlikli skor.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from server.sorular import sorular as soru_seti

# jev-1.13: girdi tokeni basina 0.042 USD / milyon. Cikti tokenlari ucretsiz.
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000


# --------------------------------------------------------------------------- #
# Kod tarafi: kesin filtreler
# --------------------------------------------------------------------------- #

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Iki koordinat arasi kus ucusu mesafe (km)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def point_in_polygon(lat: float, lon: float, polygon: list[list[float]]) -> bool:
    """Ray casting. polygon: [[lat, lon], ...]"""
    inside = False
    n = len(polygon)
    for i in range(n):
        y1, x1 = polygon[i]
        y2, x2 = polygon[(i + 1) % n]
        if (y1 > lat) != (y2 > lat):
            x_at = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < x_at:
                inside = not inside
    return inside


@dataclass
class Kriterler:
    """Kullanicinin kesin sinirlari. Hepsi kodda uygulanir."""

    max_fiyat: float | None = None
    min_fiyat: float | None = None
    min_m2: float | None = None
    max_aidat: float | None = None
    sadece_bos: bool = False
    merkez: list[float] | None = None          # [lat, lon]
    yaricap_km: float | None = None
    poligon: list[list[float]] | None = None   # haritada cizilen alan
    profil: str = "Günlük kullanım, uzun vadeli oturum"
    oncelikler: str = "Ulaşım kolaylığı, düşük aidat, taşınmaya hazır olmak"
    kirmizi_cizgiler: str = "Kiracılı teslim, tapu sorunu"


@dataclass
class Eleme:
    """Bir ilanin kod filtresinden gecip gecmedigi ve nedeni."""

    gecti: bool
    neden: str | None = None
    mesafe_km: float | None = None


def kod_filtresi(ilan: dict[str, Any], k: Kriterler) -> Eleme:
    fields = ilan.get("fields") or {}
    fiyat = ilan.get("fiyat_tl")

    if k.max_fiyat is not None and fiyat is not None and fiyat > k.max_fiyat:
        return Eleme(False, f"fiyat {fiyat:,.0f} > {k.max_fiyat:,.0f}".replace(",", "."))
    if k.min_fiyat is not None and fiyat is not None and fiyat < k.min_fiyat:
        return Eleme(False, f"fiyat {fiyat:,.0f} < {k.min_fiyat:,.0f}".replace(",", "."))

    m2 = fields.get("m2_net") or fields.get("m2_brut")
    if k.min_m2 is not None and m2 is not None and m2 < k.min_m2:
        return Eleme(False, f"{m2:.0f} m² < {k.min_m2:.0f} m²")

    aidat = fields.get("aidat_tl")
    if k.max_aidat is not None and aidat is not None and aidat > k.max_aidat:
        return Eleme(False, f"aidat {aidat:,.0f} > {k.max_aidat:,.0f}".replace(",", "."))

    if k.sadece_bos and fields.get("kullanim_durumu") and fields["kullanim_durumu"] != "Boş":
        return Eleme(False, f"kullanım durumu: {fields['kullanim_durumu']}")

    mesafe = None
    coords = ilan.get("coords")
    if coords and k.merkez:
        mesafe = haversine_km(coords["lat"], coords["lon"], k.merkez[0], k.merkez[1])
        if k.yaricap_km is not None and mesafe > k.yaricap_km:
            return Eleme(False, f"merkeze {mesafe:.1f} km > {k.yaricap_km:.1f} km", mesafe)

    if coords and k.poligon and len(k.poligon) >= 3:
        if not point_in_polygon(coords["lat"], coords["lon"], k.poligon):
            return Eleme(False, "çizilen alanın dışında", mesafe)

    return Eleme(True, None, mesafe)


# --------------------------------------------------------------------------- #
# Jev tarafi: yalnizca metinden cikan yargilar
# --------------------------------------------------------------------------- #

sorular = soru_seti  # sorular.py'de tanimli; burada yeniden disa aktariliyor


def durum(ilan: dict[str, Any], k: Kriterler) -> dict[str, Any]:
    """Jev'e gonderilecek state. Yalnizca yargiya konu olan kisimlar."""
    fields = dict(ilan.get("fields") or {})
    return {
        "baslik": ilan.get("baslik"),
        "yapilandirilmis_alanlar": fields,
        "aciklama": (ilan.get("aciklama") or "")[:6000],
        "konum_yolu": ilan.get("konum_yolu", []),
        "alici_profili": {
            "kullanim": k.profil,
            "oncelikler": k.oncelikler,
            "kirmizi_cizgiler": k.kirmizi_cizgiler,
        },
    }


# --------------------------------------------------------------------------- #
# Karar: kirmizi bayraklar ayri, tercihler agirlikli
# --------------------------------------------------------------------------- #

AGIRLIKLAR = {
    "profile_uygunluk": 0.35,
    "ulasim_erisilebilirlik": 0.20,
    "site_olanaklari": 0.15,
    "bilgi_doygunlugu": 0.10,
    "konum_vaadi_somutlugu": 0.10,
    "satis_aciliyeti": 0.10,
}


BAYRAK_ESIGI = 0.6
KARARSIZ_ALT = 0.35
SKOR_ESIGI = 0.55
GUVEN_ESIGI = 0.55


@dataclass
class Karar:
    sonuc: str                       # "ele" | "kisa_liste" | "sana_sor"
    skor: float
    bayraklar: list[str] = field(default_factory=list)
    gerekce: list[str] = field(default_factory=list)
    # Asagidakiler kararin nasil olustugunu adim adim gosterebilmek icin:
    kapilar: list[dict[str, Any]] = field(default_factory=list)
    terimler: list[dict[str, Any]] = field(default_factory=list)


def karar_ver(cevaplar: Any) -> Karar:
    nouls = cevaplar.nouls
    scores = cevaplar.scores
    choices = cevaplar.choices

    # --- 1. kapi: kirmizi bayraklar. Agirlikli skora karismaz; tek basina eler.
    bayrak_tanimlari = [
        ("kiracili_ima", "kiracılı olabilir"),
        ("celiskili_bilgi", "bilgiler çelişkili"),
    ]
    bayraklar: list[str] = []
    kapilar: list[dict[str, Any]] = []
    for ad, etiket in bayrak_tanimlari:
        deger = nouls[ad].noul
        acik = deger > BAYRAK_ESIGI
        kapilar.append({
            "tur": "bayrak", "ad": ad, "etiket": etiket,
            "deger": round(deger, 3), "esik": BAYRAK_ESIGI, "tetikledi": acik,
            "kosul": f"> {BAYRAK_ESIGI}",
        })
        if acik:
            bayraklar.append(etiket)

    # Choice tabanli bayrak: metin acikca kiracili teslim diyorsa Noul'dan bagimsiz eler.
    teslim = choices["teslim_durumu"]
    teslim_kiracili = teslim.choice == "kiracili" and teslim.confidence > 0.6
    kapilar.append({
        "tur": "bayrak", "ad": "teslim_durumu", "etiket": "metin kiracılı teslim diyor",
        "deger": round(teslim.probabilities.get("kiracili", 0.0), 3), "esik": 0.6,
        "tetikledi": teslim_kiracili, "secim": teslim.choice, "kosul": "seçim kiracılı ve güven > 0.6",
    })
    if teslim_kiracili and "kiracılı olabilir" not in bayraklar:
        bayraklar.append("metin kiracılı teslim diyor")

    # --- 2. agirlikli skor: her Score kendi seviye sayisina gore 0-1'e normalize edilir.
    skor = 0.0
    terimler: list[dict[str, Any]] = []
    for ad, agirlik in AGIRLIKLAR.items():
        answer = scores[ad]
        en_ust = max(answer.probabilities)
        normalize = (answer.score / en_ust) if en_ust else 0.0
        katki = agirlik * normalize
        skor += katki
        terimler.append({
            "ad": ad, "ham": round(answer.score, 2), "en_ust": en_ust,
            "normalize": round(normalize, 4), "agirlik": agirlik,
            "katki": round(katki, 4), "guven": round(answer.confidence, 3),
        })

    # --- 3. kapi: belirsizlik. Dusuk guven ya da kararsiz Noul -> insana birak.
    belirsiz: list[str] = []
    guven = choices["satici_dili"].confidence
    kapilar.append({
        "tur": "belirsizlik", "ad": "satici_dili", "etiket": "satıcı dili belirsiz",
        "deger": round(guven, 3), "esik": GUVEN_ESIGI, "tetikledi": guven < GUVEN_ESIGI,
        "kosul": f"güven < {GUVEN_ESIGI}",
    })
    if guven < GUVEN_ESIGI:
        belirsiz.append("satıcı dili belirsiz")

    yetersiz = nouls["metin_yetersiz"].noul
    kapilar.append({
        "tur": "belirsizlik", "ad": "metin_yetersiz", "etiket": "ilan metni yetersiz",
        "deger": round(yetersiz, 3), "esik": BAYRAK_ESIGI, "tetikledi": yetersiz > BAYRAK_ESIGI,
        "kosul": f"> {BAYRAK_ESIGI}",
    })
    if yetersiz > BAYRAK_ESIGI:
        belirsiz.append("ilan metni yetersiz")

    for ad, _ in bayrak_tanimlari:
        deger = nouls[ad].noul
        kararsiz = KARARSIZ_ALT < deger <= BAYRAK_ESIGI
        kapilar.append({
            "tur": "kararsiz", "ad": ad, "etiket": f"{ad} kararsız",
            "deger": round(deger, 3), "esik": KARARSIZ_ALT, "tetikledi": kararsiz,
            "kosul": f"{KARARSIZ_ALT} – {BAYRAK_ESIGI} arası",
        })
        if kararsiz:
            belirsiz.append(f"{ad} kararsız")

    ortak = {"kapilar": kapilar, "terimler": terimler}
    if bayraklar:
        return Karar("ele", skor, bayraklar, [f"kırmızı bayrak: {b}" for b in bayraklar], **ortak)
    if belirsiz:
        return Karar("sana_sor", skor, bayraklar, belirsiz, **ortak)
    if skor < SKOR_ESIGI:
        return Karar("ele", skor, bayraklar, [f"uygunluk skoru düşük ({skor:.2f})"], **ortak)
    return Karar("kisa_liste", skor, bayraklar, [f"uygunluk skoru {skor:.2f}"], **ortak)


def olcum(baslangic: float, usage: Any) -> dict[str, Any]:
    """Bir kararin suresi ve maliyeti."""
    ms = (time.perf_counter() - baslangic) * 1000
    tokens = getattr(usage, "input_tokens", None) or 0
    return {"ms": round(ms, 1), "input_tokens": tokens, "usd": round(tokens * USD_PER_INPUT_TOKEN, 8)}
