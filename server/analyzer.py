"""Kod filtresi + Jev yargilari + agirlikli skor.

Is bolumu kasitli:
  - Sayisal ve kesin olan her sey KODDA (fiyat, alan, km, yil, aidat, mesafe).
    Jev sayilarda zayif ve bu filtreler zaten kesin.
  - Jev'e yalnizca metinden cikan yargilar sorulur: celiski, abarti, satici dili,
    profile uygunluk. Bunlari kod yapamaz.
  - Nihai karar yine kodda: kirmizi bayraklar ayri kosul, tercihler agirlikli skor.

Soru setleri kategoriye gore secilir (emlak / vasita) ve kullanicinin kendi
ekledigi sorularla birlestirilir. Yerlesik sorular degistirilemez; ek sorular
istenildigi an temizlenip varsayilana donulebilir.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from typesafe_sdk import Choice, Noul, Score

from server.sorular import sorular as sorular_emlak
from server.sorular_vasita import AGIRLIKLAR_VASITA, BAYRAKLAR_VASITA, sorular_vasita

# jev-1.13: girdi tokeni basina 0.042 USD / milyon. Cikti tokenlari ucretsiz.
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000

BAYRAK_ESIGI = 0.6
KARARSIZ_ALT = 0.48
SKOR_ESIGI = 0.55
GUVEN_ESIGI = 0.55


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
    max_km: float | None = None          # vasita
    min_yil: float | None = None         # vasita
    merkez: list[float] | None = None    # [lat, lon]
    yaricap_km: float | None = None
    poligon: list[list[float]] | None = None
    profil: str = "Günlük kullanım, uzun vadeli"
    oncelikler: str = "Düşük işletme maliyeti, bakımlı olması"
    kirmizi_cizgiler: str = "Bilgilerin çelişkili olması"


@dataclass
class Eleme:
    gecti: bool
    neden: str | None = None
    mesafe_km: float | None = None


def _nokta(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def kod_filtresi(ilan: dict[str, Any], k: Kriterler) -> Eleme:
    fields = ilan.get("fields") or {}
    fiyat = ilan.get("fiyat_tl")

    if k.max_fiyat is not None and fiyat is not None and fiyat > k.max_fiyat:
        return Eleme(False, f"fiyat {_nokta(fiyat)} > {_nokta(k.max_fiyat)}")
    if k.min_fiyat is not None and fiyat is not None and fiyat < k.min_fiyat:
        return Eleme(False, f"fiyat {_nokta(fiyat)} < {_nokta(k.min_fiyat)}")

    m2 = fields.get("m2_net") or fields.get("m2_brut")
    if k.min_m2 is not None and m2 is not None and m2 < k.min_m2:
        return Eleme(False, f"{m2:.0f} m² < {k.min_m2:.0f} m²")

    aidat = fields.get("aidat_tl")
    if k.max_aidat is not None and aidat is not None and aidat > k.max_aidat:
        return Eleme(False, f"aidat {_nokta(aidat)} > {_nokta(k.max_aidat)}")

    if k.sadece_bos and fields.get("kullanim_durumu") and fields["kullanim_durumu"] != "Boş":
        return Eleme(False, f"kullanım durumu: {fields['kullanim_durumu']}")

    km = fields.get("km")
    if k.max_km is not None and km is not None and km > k.max_km:
        return Eleme(False, f"{_nokta(km)} km > {_nokta(k.max_km)} km")

    yil = fields.get("yil")
    if k.min_yil is not None and yil is not None and yil < k.min_yil:
        return Eleme(False, f"{yil:.0f} model < {k.min_yil:.0f}")

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
# Soru setleri: yerlesik + kullanicinin ekledikleri
# --------------------------------------------------------------------------- #

AGIRLIKLAR_EMLAK = {
    "profile_uygunluk": 0.35,
    "ulasim_erisilebilirlik": 0.20,
    "site_olanaklari": 0.15,
    "bilgi_doygunlugu": 0.10,
    "konum_vaadi_somutlugu": 0.10,
    "satis_aciliyeti": 0.10,
}

BAYRAKLAR_EMLAK = [
    ("kiracili_ima", "kiracılı olabilir"),
    ("celiskili_bilgi", "bilgiler çelişkili"),
]

KATEGORILER = {
    "emlak": (sorular_emlak, AGIRLIKLAR_EMLAK, BAYRAKLAR_EMLAK),
    "vasita": (sorular_vasita, AGIRLIKLAR_VASITA, BAYRAKLAR_VASITA),
}


def kategori_coz(ad: str | None) -> str:
    return ad if ad in KATEGORILER else "emlak"


def ek_soruya_cevir(e: dict[str, Any]) -> Any:
    """Kullanicinin tanimladigi bir soruyu SDK nesnesine cevirir."""
    tip = e.get("tip")
    yonerge = e.get("instructions") or ""
    if tip == "noul":
        kriter = {k: v for k, v in (("true", e.get("true")), ("false", e.get("false"))) if v}
        return Noul(instructions=yonerge, criteria=kriter or None)
    if tip == "score":
        seviyeler = [s for s in (e.get("seviyeler") or []) if s]
        if len(seviyeler) < 2:
            raise ValueError("score sorusu en az iki seviye ister")
        return Score(instructions=yonerge, criteria=seviyeler)
    if tip == "choice":
        secenekler = {k: v for k, v in (e.get("secenekler") or {}).items() if k}
        if len(secenekler) < 2:
            raise ValueError("choice sorusu en az iki seçenek ister")
        return Choice(instructions=yonerge, criteria=secenekler)
    raise ValueError(f"bilinmeyen soru tipi: {tip}")


def sorular(kategori: str = "emlak", ekler: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Kategorinin yerlesik sorulari + kullanicinin ekledikleri.

    Ek sorular yerlesikleri EZEMEZ: ayni ada sahip bir ek soru atlanir. Boylece
    'varsayilana don' her zaman calisir ve yerlesik davranis bozulamaz.
    """
    uret, _, _ = KATEGORILER[kategori_coz(kategori)]
    hepsi = dict(uret())
    for e in ekler or []:
        ad = (e.get("ad") or "").strip()
        if not ad or ad in hepsi:
            continue
        if e.get("kategori") not in (None, "", "hepsi", kategori_coz(kategori)):
            continue
        try:
            hepsi[ad] = ek_soruya_cevir(e)
        except (ValueError, TypeError):
            continue
    return hepsi


def agirliklar(kategori: str, ekler: list[dict[str, Any]] | None = None) -> dict[str, float]:
    """Yerlesik agirliklar + agirlik verilmis ek Score sorulari, toplami 1'e normalize."""
    _, temel, _ = KATEGORILER[kategori_coz(kategori)]
    w = dict(temel)
    for e in ekler or []:
        ad = (e.get("ad") or "").strip()
        if e.get("tip") != "score" or not ad or ad in w:
            continue
        try:
            a = float(e.get("agirlik") or 0)
        except (TypeError, ValueError):
            a = 0.0
        if a > 0:
            w[ad] = a
    toplam = sum(w.values())
    return {k: v / toplam for k, v in w.items()} if toplam else w


def bayraklar_tanimi(kategori: str, ekler: list[dict[str, Any]] | None = None) -> list[tuple[str, str]]:
    """Yerlesik kirmizi bayraklar + bayrak isaretli ek Noul sorulari."""
    _, _, temel = KATEGORILER[kategori_coz(kategori)]
    out = list(temel)
    for e in ekler or []:
        ad = (e.get("ad") or "").strip()
        if e.get("tip") == "noul" and e.get("bayrak") and ad:
            out.append((ad, e.get("etiket") or ad.replace("_", " ")))
    return out


def durum(ilan: dict[str, Any], k: Kriterler) -> dict[str, Any]:
    """Jev'e gonderilecek state. Yalnizca yargiya konu olan kisimlar."""
    state: dict[str, Any] = {
        "baslik": ilan.get("baslik"),
        "yapilandirilmis_alanlar": dict(ilan.get("fields") or {}),
        "aciklama": (ilan.get("aciklama") or "")[:6000],
        "konum_yolu": ilan.get("konum_yolu", []),
        "alici_profili": {
            "kullanim": k.profil,
            "oncelikler": k.oncelikler,
            "kirmizi_cizgiler": k.kirmizi_cizgiler,
        },
    }
    # Vasita: govde semasi metinden cikarilamaz, ayri bir alan olarak verilir.
    hasar = ilan.get("hasar")
    if hasar:
        state["hasar_semasi"] = {
            "ozet": hasar.get("ozet"),
            "orijinal": hasar.get("orijinal", []),
            "lokal_boyali": hasar.get("lokal_boyali", []),
            "boyali": hasar.get("boyali", []),
            "degisen": hasar.get("degisen", []),
        }
    return state


# --------------------------------------------------------------------------- #
# Karar: kirmizi bayraklar ayri, tercihler agirlikli
# --------------------------------------------------------------------------- #

@dataclass
class Karar:
    sonuc: str                       # "ele" | "kisa_liste" | "sana_sor"
    skor: float
    bayraklar: list[str] = field(default_factory=list)
    gerekce: list[str] = field(default_factory=list)
    kapilar: list[dict[str, Any]] = field(default_factory=list)
    terimler: list[dict[str, Any]] = field(default_factory=list)


def karar_ver(
    cevaplar: Any,
    kategori: str = "emlak",
    ekler: list[dict[str, Any]] | None = None,
    ilan: dict[str, Any] | None = None,
) -> Karar:
    nouls, scores, choices = cevaplar.nouls, cevaplar.scores, cevaplar.choices
    bayrak_tanimlari = bayraklar_tanimi(kategori, ekler)
    w = agirliklar(kategori, ekler)

    # --- 1. kapi: kirmizi bayraklar. Agirlikli skora karismaz; tek basina eler.
    bayraklar: list[str] = []
    kapilar: list[dict[str, Any]] = []
    for ad, etiket in bayrak_tanimlari:
        if ad not in nouls:
            continue
        deger = nouls[ad].noul
        acik = deger > BAYRAK_ESIGI
        kapilar.append({
            "tur": "bayrak", "ad": ad, "etiket": etiket, "deger": round(deger, 3),
            "esik": BAYRAK_ESIGI, "tetikledi": acik, "kosul": f"> {BAYRAK_ESIGI}",
        })
        if acik:
            bayraklar.append(etiket)

    # Emlakta metin acikca kiracili teslim diyorsa Noul'dan bagimsiz eler.
    teslim = choices.get("teslim_durumu")
    if teslim is not None:
        tetik = teslim.choice == "kiracili" and teslim.confidence > 0.6
        kapilar.append({
            "tur": "bayrak", "ad": "teslim_durumu", "etiket": "metin kiracılı teslim diyor",
            "deger": round(teslim.probabilities.get("kiracili", 0.0), 3), "esik": 0.6,
            "tetikledi": tetik, "secim": teslim.choice,
            "kosul": "seçim kiracılı ve güven > 0.6",
        })
        if tetik and "kiracılı olabilir" not in bayraklar:
            bayraklar.append("metin kiracılı teslim diyor")

    # Vasita hasar kapisi — KOD karari, model karari degil.
    #
    # Once modele "ilan semayla celisiyor mu" diye Noul soruyordu ve bu surekli
    # 0.5 civarinda kaliyordu: baslik "hasar kaydi yok" derken (tramer kaydi
    # gercekten yok) aciklama degisen parcalari kabul edebiliyor. Model hakli
    # olarak ikircikli kaliyor, her ilan insana dusuyordu.
    #
    # Oysa sema zaten yapilandirilmis veri. Celiskiyi kod kesin olarak kurar:
    # metin "tamamen hasarsiz" diyorsa VE semada orijinal disi panel varsa celiski
    # vardir. Metin kismi kabul ediyorsa celiski yoktur, panel sayisi kac olursa olsun.
    beyan = choices.get("hasar_beyani")
    hasar = (ilan or {}).get("hasar") or {}
    orijinal_disi = hasar.get("orijinal_disi")
    if beyan is not None and orijinal_disi is not None:
        hasarsiz_iddia = beyan.choice == "tamamen_hasarsiz" and beyan.confidence > 0.6
        tetik = hasarsiz_iddia and orijinal_disi > 0
        kapilar.append({
            "tur": "bayrak", "ad": "hasar_beyani", "etiket": "ilan hasar şemasıyla çelişiyor",
            "deger": float(orijinal_disi), "esik": 0,
            "tetikledi": tetik, "secim": beyan.choice,
            "kosul": "metin tamamen hasarsız diyor ve şemada orijinal dışı panel var",
            "not": hasar.get("ozet"),
        })
        if tetik:
            bayraklar.append(f"metin hasarsız diyor ama {orijinal_disi} panel orijinal değil")

    # --- 2. agirlikli skor
    skor = 0.0
    terimler: list[dict[str, Any]] = []
    for ad, agirlik in w.items():
        answer = scores.get(ad)
        if answer is None:
            continue
        en_ust = max(answer.probabilities) if answer.probabilities else 0
        normalize = (answer.score / en_ust) if en_ust else 0.0
        katki = agirlik * normalize
        skor += katki
        terimler.append({
            "ad": ad, "ham": round(answer.score, 2), "en_ust": en_ust,
            "normalize": round(normalize, 4), "agirlik": round(agirlik, 4),
            "katki": round(katki, 4), "guven": round(answer.confidence, 3),
        })

    # --- 3. kapi: belirsizlik
    belirsiz: list[str] = []
    satici = choices.get("satici_dili")
    if satici is not None:
        tetik = satici.confidence < GUVEN_ESIGI
        kapilar.append({
            "tur": "belirsizlik", "ad": "satici_dili", "etiket": "satıcı dili belirsiz",
            "deger": round(satici.confidence, 3), "esik": GUVEN_ESIGI, "tetikledi": tetik,
            "kosul": f"güven < {GUVEN_ESIGI}",
        })
        if tetik:
            belirsiz.append("satıcı dili belirsiz")

    for ad, etiket in (("metin_yetersiz", "ilan metni yetersiz"),):
        if ad not in nouls:
            continue
        deger = nouls[ad].noul
        tetik = deger > BAYRAK_ESIGI
        kapilar.append({
            "tur": "belirsizlik", "ad": ad, "etiket": etiket, "deger": round(deger, 3),
            "esik": BAYRAK_ESIGI, "tetikledi": tetik, "kosul": f"> {BAYRAK_ESIGI}",
        })
        if tetik:
            belirsiz.append(etiket)

    for ad, _ in bayrak_tanimlari:
        if ad not in nouls:
            continue
        deger = nouls[ad].noul
        tetik = KARARSIZ_ALT < deger <= BAYRAK_ESIGI
        kapilar.append({
            "tur": "kararsiz", "ad": ad, "etiket": f"{ad} kararsız", "deger": round(deger, 3),
            "esik": KARARSIZ_ALT, "tetikledi": tetik,
            "kosul": f"{KARARSIZ_ALT} – {BAYRAK_ESIGI} arası",
        })
        if tetik:
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
