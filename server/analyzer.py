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

from typesafe_sdk import Choice, Noul, Score

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

def sorular() -> dict[str, Any]:
    return {
        # --- kirmizi bayraklar: her biri ayri Noul, cunku birden fazlasi ayni anda dogru olabilir
        "kiracili_ima": Noul(
            instructions=(
                "İlan metni, dairenin şu anda kiracılı olduğunu veya alıcıya kiracıyla "
                "birlikte teslim edileceğini söylüyor ya da ima ediyor."
            ),
            criteria={
                "true": "Metinde kiracı, kira kontratı, kiracılı teslim, gelir getiren gibi ifadeler geçiyor",
                "false": "Metin boş/sıfır olduğunu söylüyor ya da kiracı konusuna hiç değinmiyor",
            },
        ),
        "celiskili_bilgi": Noul(
            instructions=(
                "`yapilandirilmis_alanlar` içindeki bilgilerle `aciklama` metni birbiriyle çelişiyor. "
                "Örnek: alanlarda 'Kullanım Durumu: Boş' yazarken açıklamada kiracıdan söz edilmesi, "
                "ya da alanlarda yazan oda sayısı/kat bilgisinin açıklamada farklı verilmesi."
            ),
            criteria={
                "true": "En az bir konuda alanlar ile açıklama birbirini tutmuyor",
                "false": "Açıklama, yapılandırılmış alanlarla tutarlı ya da o konulara hiç değinmiyor",
            },
        ),
        "metin_yetersiz": Noul(
            instructions=(
                "Açıklama metni, dairenin durumu hakkında karar vermeye yetecek bilgi içermiyor; "
                "sadece genel reklam cümlelerinden oluşuyor."
            ),
        ),
        # --- sinifllandirma
        "satici_dili": Choice(
            instructions=(
                "`aciklama` metninin diline bakarak ilanı kimin yazdığını belirle. "
                "`yapilandirilmis_alanlar.kimden` etiketini değil, metnin kendisini esas al."
            ),
            criteria={
                "ev_sahibi": "Dairede oturan veya sahibi olan kişinin kendi ağzından anlatımı",
                "emlak_ofisi": "Kurumsal emlak pazarlama dili, portföy/danışman anlatımı",
                "belirsiz": "Metinden hangisi olduğu anlaşılmıyor",
            },
        ),
        # --- dereceler
        "konum_vaadi_somutlugu": Score(
            instructions=(
                "Açıklamadaki konum ve ulaşım iddialarının ne kadar somut olduğunu değerlendir. "
                "İddiaların doğru olup olmadığını değil, ne kadar doğrulanabilir yazıldığını puanla."
            ),
            criteria=[
                "Konumdan hiç söz edilmiyor",
                "Sadece 'merkezi konumda', 'her yere yakın' gibi genel ifadeler var",
                "Bazı yerlere mesafe verilmiş ama belirsiz",
                "Adı verilmiş yerlere somut mesafe veya süre belirtilmiş",
            ],
        ),
        "site_olanaklari": Score(
            instructions="Açıklamada anlatılan site ve bina olanaklarının kapsamı.",
            criteria=[
                "Site veya ortak olanaktan söz edilmiyor",
                "Temel düzeyde: güvenlik veya otopark var",
                "Orta düzey: güvenlik, otopark ve en az bir sosyal alan",
                "Geniş: havuz, spor salonu, çocuk alanı gibi birden çok sosyal olanak",
            ],
        ),
        "profile_uygunluk": Score(
            instructions=(
                "İlanın, `alici_profili` içinde tarif edilen kullanım ve önceliklere uygunluğu. "
                "Sadece açıklama ve yapılandırılmış alanlardaki bilgiye dayan."
            ),
            criteria=[
                "Alıcının önceliklerine açıkça aykırı",
                "Zayıf uyum: birkaç önceliği karşılıyor",
                "İyi uyum: önceliklerin çoğunu karşılıyor",
                "Tarif edilen kullanıma birebir uyuyor",
            ],
        ),
        "satis_aciliyeti": Score(
            instructions="Satıcının aciliyet düzeyi; pazarlık payı olup olmadığının sinyali.",
            criteria=[
                "Acele yok; pazarlık kabul edilmediği belirtilmiş",
                "Normal bir satış ilanı",
                "Acil satılık, takas olur, pazarlık payı var gibi ifadeler var",
            ],
        ),
    }


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

AGIRLIKLAR = {"profile_uygunluk": 0.45, "konum_vaadi_somutlugu": 0.20, "site_olanaklari": 0.20, "satis_aciliyeti": 0.15}


@dataclass
class Karar:
    sonuc: str                       # "ele" | "kisa_liste" | "sana_sor"
    skor: float
    bayraklar: list[str] = field(default_factory=list)
    gerekce: list[str] = field(default_factory=list)


def karar_ver(cevaplar: Any) -> Karar:
    nouls = cevaplar.nouls
    scores = cevaplar.scores
    choices = cevaplar.choices

    bayraklar: list[str] = []
    if nouls["kiracili_ima"].noul > 0.6:
        bayraklar.append("kiracılı olabilir")
    if nouls["celiskili_bilgi"].noul > 0.6:
        bayraklar.append("bilgiler çelişkili")

    # Agirlikli skor: her Score kendi seviye sayisina gore 0-1'e normalize edilir.
    skor = 0.0
    for ad, agirlik in AGIRLIKLAR.items():
        answer = scores[ad]
        en_ust = max(answer.probabilities)
        skor += agirlik * (answer.score / en_ust if en_ust else 0.0)

    # Belirsizlik: dusuk guven ya da kararsiz Noul -> insana birak.
    belirsiz: list[str] = []
    if choices["satici_dili"].confidence < 0.55:
        belirsiz.append("satıcı dili belirsiz")
    if nouls["metin_yetersiz"].noul > 0.6:
        belirsiz.append("ilan metni yetersiz")
    for ad in ("kiracili_ima", "celiskili_bilgi"):
        if 0.35 < nouls[ad].noul <= 0.6:
            belirsiz.append(f"{ad} kararsız")

    if bayraklar:
        return Karar("ele", skor, bayraklar, [f"kırmızı bayrak: {b}" for b in bayraklar])
    if belirsiz:
        return Karar("sana_sor", skor, bayraklar, belirsiz)
    if skor < 0.55:
        return Karar("ele", skor, bayraklar, [f"uygunluk skoru düşük ({skor:.2f})"])
    return Karar("kisa_liste", skor, bayraklar, [f"uygunluk skoru {skor:.2f}"])


def olcum(baslangic: float, usage: Any) -> dict[str, Any]:
    """Bir kararin suresi ve maliyeti."""
    ms = (time.perf_counter() - baslangic) * 1000
    tokens = getattr(usage, "input_tokens", None) or 0
    return {"ms": round(ms, 1), "input_tokens": tokens, "usd": round(tokens * USD_PER_INPUT_TOKEN, 8)}
