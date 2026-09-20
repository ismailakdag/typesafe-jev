"""Yerel ilan arsivi.

Tarayici eklentisi yakaladigi kayitlari buraya gonderir. Sunucu sadece 127.0.0.1'e
baglanir; veri makineden disari cikmaz.

Calistir:  uv run python -m server.app
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typesafe_sdk import AsyncTypeSafeClient

from server import analyzer, transkript

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "ilanlar"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SAFE_ID = re.compile(r"[^a-z0-9._-]+")

app = FastAPI(title="Ilan Arsivi")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # yalnizca 127.0.0.1'e baglaniyoruz; tarayici eklentisi icin gerekli
    allow_methods=["*"],
    allow_headers=["*"],
)


class Capture(BaseModel):
    """Eklentiden gelen ham kayit. Bilinmeyen alanlar da saklanir."""

    model_config = {"extra": "allow"}

    site: str
    url: str
    captured_at: str
    baslik: str | None = None
    ilan_no: str | None = None
    fiyat_tl: float | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    coords: dict[str, Any] | None = None


def record_id(capture: Capture) -> str:
    """Site + ilan numarasindan kararli bir dosya adi uretir."""
    key = capture.ilan_no or re.sub(r"\W+", "-", capture.url.rsplit("/", 2)[-2] if "/" in capture.url else capture.url)
    return SAFE_ID.sub("-", f"{capture.site}-{key}".lower()).strip("-")[:120]


def path_for(rid: str) -> Path:
    return DATA_DIR / f"{rid}.json"


def load(rid: str) -> dict[str, Any] | None:
    path = path_for(rid)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@app.post("/capture")
def capture(payload: Capture) -> dict[str, Any]:
    """Bir yakalamayi arsive ekler.

    Ayni ilan tekrar yakalanirsa uzerine yazmaz, yeni bir surum olarak eklenir:
    boylece fiyat ve aciklama degisiklikleri zaman icinde takip edilebilir.
    """
    rid = record_id(payload)
    snapshot = payload.model_dump()
    existing = load(rid)

    if existing is None:
        existing = {
            "id": rid,
            "site": payload.site,
            "url": payload.url,
            "ilan_no": payload.ilan_no,
            "first_seen": payload.captured_at,
            "captures": [],
        }

    existing["last_seen"] = payload.captured_at
    existing["url"] = payload.url
    existing["captures"].append(snapshot)
    path_for(rid).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "id": rid,
        "capture_count": len(existing["captures"]),
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize(doc: dict[str, Any]) -> dict[str, Any]:
    """Listeleme icin son surumun ozeti; fiyat degisimi varsa isaretlenir."""
    latest = doc["captures"][-1]
    prices = [c.get("fiyat_tl") for c in doc["captures"] if c.get("fiyat_tl")]
    foto = latest.get("foto") or []
    return {
        "id": doc["id"],
        "site": doc["site"],
        "url": doc["url"],
        "baslik": latest.get("baslik"),
        "fiyat_tl": latest.get("fiyat_tl"),
        "ilk_fiyat_tl": prices[0] if prices else None,
        "fiyat_degisti": len(set(prices)) > 1,
        "coords": latest.get("coords"),
        "konum_yolu": latest.get("konum_yolu", []),
        "fields": latest.get("fields", {}),
        "aciklama": latest.get("aciklama"),
        "kapak": foto[0] if foto else None,
        "foto_sayisi": len(foto),
        "kategori": latest.get("kategori") or "emlak",
        "hasar": latest.get("hasar"),
        "karar": latest.get("karar"),
        "capture_count": len(doc["captures"]),
        "first_seen": doc.get("first_seen"),
        "last_seen": doc.get("last_seen"),
        "extraction": latest.get("_extraction", {}),
    }


def all_summaries() -> list[dict[str, Any]]:
    docs = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            docs.append(summarize(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
    return docs


@app.get("/api/ilanlar")
def list_ilanlar() -> dict[str, Any]:
    docs = all_summaries()
    return {"count": len(docs), "ilanlar": docs}


def karar_kaydet(rid: str, karar: dict[str, Any]) -> None:
    """Toplu elemenin verdigi karari arsivdeki son surume yazar.

    Karar, o surumun icerigi uzerinde verildigi icin oraya ait. Boylece panel
    yeniden acildiginda karar yeniden cagri yapilmadan gosterilebiliyor.
    """
    doc = load(rid)
    if doc is None or not doc.get("captures"):
        return
    doc["captures"][-1]["karar"] = {**karar, "verildi": datetime.now(timezone.utc).isoformat()}
    path_for(rid).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


@app.delete("/api/ilan/{rid}")
def delete_ilan(rid: str) -> dict[str, Any]:
    """Bir ilani arsivden siler. Tum surumleriyle birlikte gider."""
    path = path_for(SAFE_ID.sub("-", rid.lower()))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    path.unlink()
    return {"silindi": rid}


# --------------------------------------------------------------------------- #
# Ayarlar: API anahtari .env dosyasina yazilir
# --------------------------------------------------------------------------- #

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def mask(secret: str) -> str:
    """Anahtari ekranda gostermek icin maskeler; tam degeri hicbir yanitta donmez."""
    if not secret:
        return ""
    if len(secret) <= 10:
        return secret[:2] + "…"
    return f"{secret[:6]}…{secret[-4:]}"


def write_env_var(name: str, value: str) -> None:
    """.env icindeki tek satiri gunceller, diger satirlara dokunmaz."""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    out, yazildi = [], False
    for raw in lines:
        if raw.strip().startswith(f"{name}="):
            out.append(f"{name}={value}")
            yazildi = True
        else:
            out.append(raw)
    if not yazildi:
        out.append(f"{name}={value}")
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


class AyarlarIn(BaseModel):
    api_key: str


@app.get("/api/ayarlar")
def get_ayarlar() -> dict[str, Any]:
    key = os.getenv("TYPESAFE_API_KEY", "")
    return {
        "anahtar_var": bool(key),
        "maskeli": mask(key),
        "env_yolu": str(ENV_PATH),
        "env_var": ENV_PATH.exists(),
    }


@app.post("/api/ayarlar")
def set_ayarlar(body: AyarlarIn) -> dict[str, Any]:
    """Anahtari .env'ye yazar ve calisan surece uygular; yeniden baslatma gerekmez."""
    key = body.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Anahtar boş olamaz")
    write_env_var("TYPESAFE_API_KEY", key)
    os.environ["TYPESAFE_API_KEY"] = key
    return {"anahtar_var": True, "maskeli": mask(key), "env_yolu": str(ENV_PATH)}


@app.post("/api/ayarlar/dogrula")
async def dogrula() -> dict[str, Any]:
    """Anahtarin gercekten calistigini TypeSafe'e sorarak dogrular."""
    if not os.getenv("TYPESAFE_API_KEY"):
        raise HTTPException(status_code=400, detail="Önce anahtarı kaydet")
    try:
        async with AsyncTypeSafeClient() as client:
            models = await client.models.list()
        return {"ok": True, "modeller": [m.name for m in models.models]}
    except Exception as error:
        return {"ok": False, "mesaj": str(error)}


# --------------------------------------------------------------------------- #
# Eleme: kod filtresi + Jev, sonuclar tamamlandikca akitilir
# --------------------------------------------------------------------------- #

class AnalyzeRequest(BaseModel):
    max_fiyat: float | None = None
    min_fiyat: float | None = None
    min_m2: float | None = None
    max_aidat: float | None = None
    sadece_bos: bool = False
    max_km: float | None = None
    min_yil: float | None = None
    merkez: list[float] | None = None
    yaricap_km: float | None = None
    poligon: list[list[float]] | None = None
    profil: str = "Günlük kullanım, uzun vadeli oturum"
    oncelikler: str = "Ulaşım kolaylığı, düşük aidat, taşınmaya hazır olmak"
    kirmizi_cizgiler: str = "Kiracılı teslim, tapu sorunu"
    eszamanlilik: int = 8


def line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False) + "\n"


async def analyze_stream(req: AnalyzeRequest) -> AsyncIterator[str]:
    kriterler = analyzer.Kriterler(**req.model_dump(exclude={"eszamanlilik"}))
    ilanlar = all_summaries()
    yield line({"type": "start", "toplam": len(ilanlar)})

    # 1. asama: kod filtresi. Anlik ve bedava; ne kadar surdugunu de olcuyoruz.
    kod_basla = time.perf_counter()
    kalanlar = []
    for ilan in ilanlar:
        eleme = analyzer.kod_filtresi(ilan, kriterler)
        yield line({
            "type": "kod",
            "id": ilan["id"],
            "gecti": eleme.gecti,
            "neden": eleme.neden,
            "mesafe_km": round(eleme.mesafe_km, 2) if eleme.mesafe_km is not None else None,
        })
        if eleme.gecti:
            ilan["_mesafe_km"] = eleme.mesafe_km
            kalanlar.append(ilan)
    kod_ms = (time.perf_counter() - kod_basla) * 1000
    yield line({"type": "kod_bitti", "ms": round(kod_ms, 2), "kalan": len(kalanlar), "elenen": len(ilanlar) - len(kalanlar)})

    if not kalanlar:
        yield line({"type": "bitti", "ozet": {"kod_ms": round(kod_ms, 2), "jev_ms": 0, "usd": 0, "kisa_liste": 0}})
        return

    if not os.getenv("TYPESAFE_API_KEY"):
        yield line({"type": "hata", "mesaj": "TYPESAFE_API_KEY yok. .env dosyasına anahtarı ekleyip sunucuyu yeniden başlat."})
        return

    ekler = ekler_yukle()
    semaphore = asyncio.Semaphore(max(1, req.eszamanlilik))
    jev_basla = time.perf_counter()

    async with AsyncTypeSafeClient() as client:
        async def degerlendir(ilan: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                t0 = time.perf_counter()
                kat = analyzer.kategori_coz(ilan.get("kategori"))
                try:
                    cevap = await client.system_one(
                        analyzer.durum(ilan, kriterler), analyzer.sorular(kat, ekler)
                    )
                except Exception as error:  # ag, kota, dogrulama — ilani atlamak yerine bildir
                    return {"type": "karar_hata", "id": ilan["id"], "baslik": ilan["baslik"], "mesaj": str(error)}
                karar = analyzer.karar_ver(cevap, kat, ekler, ilan)
                olcum = analyzer.olcum(t0, cevap.usage)
                return {
                    "type": "karar",
                    "id": ilan["id"],
                    "sonuc": karar.sonuc,
                    "skor": round(karar.skor, 4),
                    "bayraklar": karar.bayraklar,
                    "gerekce": karar.gerekce,
                    "kapilar": karar.kapilar,
                    "terimler": karar.terimler,
                    "esikler": {
                        "bayrak": analyzer.BAYRAK_ESIGI, "kararsiz_alt": analyzer.KARARSIZ_ALT,
                        "skor": analyzer.SKOR_ESIGI, "guven": analyzer.GUVEN_ESIGI,
                    },
                    "asamalar": {"state_ms": 0.0, "model_ms": olcum["ms"], "karar_ms": 0.1},
                    "soru_sayisi": len(cevap.answers),
                    "kategori": kat,
                    "olcum": olcum,
                    "model": cevap.model,
                    "detay": {
                        "nouls": {k: round(v.noul, 3) for k, v in cevap.nouls.items()},
                        "scores": {
                            k: {"skor": round(v.score, 2), "guven": round(v.confidence, 3),
                                "seviye": v.legend,
                                "olasiliklar": {str(kk): round(vv, 3) for kk, vv in v.probabilities.items()}}
                            for k, v in cevap.scores.items()
                        },
                        "choices": {
                            k: {"secim": v.choice, "guven": round(v.confidence, 3),
                                "olasiliklar": {kk: round(vv, 3) for kk, vv in v.probabilities.items()}}
                            for k, v in cevap.choices.items()
                        },
                    },
                }

        gorevler = [asyncio.create_task(degerlendir(i)) for i in kalanlar]
        yield line({"type": "jev_basladi", "adet": len(gorevler), "eszamanlilik": req.eszamanlilik})

        toplam_usd = 0.0
        toplam_token = 0
        sayac = {"ele": 0, "kisa_liste": 0, "sana_sor": 0, "hata": 0}
        for tamamlanan in asyncio.as_completed(gorevler):
            sonuc = await tamamlanan
            if sonuc["type"] == "karar":
                toplam_usd += sonuc["olcum"]["usd"]
                toplam_token += sonuc["olcum"]["input_tokens"]
                sayac[sonuc["sonuc"]] += 1
                karar_kaydet(sonuc["id"], {k: v for k, v in sonuc.items() if k not in ("type", "id")})
            else:
                sayac["hata"] += 1
            yield line(sonuc)

    jev_ms = (time.perf_counter() - jev_basla) * 1000
    defter = ledger_yaz(toplam_token, round(toplam_usd, 10), "toplu") if toplam_token else ledger_oku()
    yield line({
        "type": "bitti",
        "ozet": {
            "kod_ms": round(kod_ms, 2),
            "jev_ms": round(jev_ms, 1),
            "toplam_ilan": len(ilanlar),
            "jev_gorulen": len(kalanlar),
            "input_tokens": toplam_token,
            "usd": round(toplam_usd, 8),
            "defter": {"cagri": defter["cagri"], "usd": defter["usd"]},
            **sayac,
        },
    })


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(analyze_stream(req), media_type="application/x-ndjson")


# --------------------------------------------------------------------------- #
# Profil: panel ile eklenti ayni olcutleri kullansin diye tek yerde tutulur
# --------------------------------------------------------------------------- #

PROFIL_PATH = DATA_DIR.parent / "profil.json"

VARSAYILAN_PROFIL = {
    "profil": "Günlük kullanım, uzun vadeli oturum. İzmir Katip Çelebi Üniversitesi'ne yakınlık önemli.",
    "oncelikler": "Ulaşım kolaylığı, düşük aidat, taşınmaya hazır olması, site içinde güvenlik ve otopark",
    "kirmizi_cizgiler": "Kiracılı teslim, tapu sorunu, bilgilerin çelişkili olması",
}


def profil_yukle() -> dict[str, str]:
    if PROFIL_PATH.exists():
        try:
            return {**VARSAYILAN_PROFIL, **json.loads(PROFIL_PATH.read_text(encoding="utf-8"))}
        except json.JSONDecodeError:
            pass
    return dict(VARSAYILAN_PROFIL)


class Profil(BaseModel):
    profil: str
    oncelikler: str
    kirmizi_cizgiler: str


@app.get("/api/profil")
def get_profil() -> dict[str, str]:
    return profil_yukle()


@app.post("/api/profil")
def set_profil(body: Profil) -> dict[str, str]:
    PROFIL_PATH.write_text(json.dumps(body.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    return body.model_dump()


# --------------------------------------------------------------------------- #
# Ek sorular: kullanicinin kendi tanimladiklari
# --------------------------------------------------------------------------- #

EK_SORULAR_PATH = DATA_DIR.parent / "ek_sorular.json"


def ekler_yukle() -> list[dict[str, Any]]:
    if EK_SORULAR_PATH.exists():
        try:
            veri = json.loads(EK_SORULAR_PATH.read_text(encoding="utf-8"))
            return veri if isinstance(veri, list) else []
        except json.JSONDecodeError:
            pass
    return []


class EkSoru(BaseModel):
    model_config = {"extra": "allow"}

    ad: str
    tip: str                      # noul | score | choice
    instructions: str
    kategori: str = "hepsi"       # emlak | vasita | hepsi
    etiket: str | None = None
    bayrak: bool = False          # noul: tek basina eleyen kirmizi bayrak olsun mu
    agirlik: float = 0.0          # score: agirlikli skora katilsin mi


def soru_ozeti(ad: str, q: Any) -> dict[str, Any]:
    """Yerlesik bir soruyu arayuzde gosterilebilir bicime cevirir."""
    d = q.model_dump()
    return {"ad": ad, "tip": d.get("type"), "instructions": d.get("instructions"), "criteria": d.get("criteria")}


@app.get("/api/sorular")
def get_sorular(kategori: str = "emlak") -> dict[str, Any]:
    kat = analyzer.kategori_coz(kategori)
    uret, _, _ = analyzer.KATEGORILER[kat]
    ekler = ekler_yukle()
    return {
        "kategori": kat,
        "yerlesik": [soru_ozeti(ad, q) for ad, q in uret().items()],
        "ekler": ekler,
        "agirliklar": analyzer.agirliklar(kat, ekler),
        "bayraklar": [ad for ad, _ in analyzer.bayraklar_tanimi(kat, ekler)],
    }


@app.post("/api/sorular")
def set_sorular(ekler: list[EkSoru]) -> dict[str, Any]:
    """Ek sorulari kaydeder. Gecersiz tanimlar reddedilir, kismi kayit yapilmaz."""
    temiz = []
    for e in ekler:
        ad = e.ad.strip()
        if not re.fullmatch(r"[a-z0-9_]{2,40}", ad):
            raise HTTPException(status_code=400, detail=f"Geçersiz ad: {e.ad} (küçük harf, rakam ve _ kullan)")
        d = e.model_dump()
        try:
            analyzer.ek_soruya_cevir(d)
        except (ValueError, TypeError) as hata:
            raise HTTPException(status_code=400, detail=f"{ad}: {hata}") from hata
        temiz.append(d)

    adlar = [e["ad"] for e in temiz]
    if len(set(adlar)) != len(adlar):
        raise HTTPException(status_code=400, detail="Aynı ad birden fazla kez kullanılmış")

    EK_SORULAR_PATH.write_text(json.dumps(temiz, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"kaydedildi": len(temiz)}


@app.delete("/api/sorular")
def reset_sorular() -> dict[str, Any]:
    """Varsayilana doner: yalnizca ek sorular silinir, yerlesikler zaten degismiyor."""
    if EK_SORULAR_PATH.exists():
        EK_SORULAR_PATH.unlink()
    return {"sifirlandi": True}


# --------------------------------------------------------------------------- #
# Kullanim defteri: her cagrinin token ve maliyeti kaydedilir
# --------------------------------------------------------------------------- #

LEDGER_PATH = DATA_DIR.parent / "kullanim.json"


def ledger_oku() -> dict[str, Any]:
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"cagri": 0, "input_tokens": 0, "usd": 0.0, "son": []}


def ledger_yaz(tokens: int, usd: float, tur: str) -> dict[str, Any]:
    d = ledger_oku()
    d["cagri"] += 1
    d["input_tokens"] += tokens
    d["usd"] = round(d["usd"] + usd, 10)
    d["son"] = ([{"ts": datetime.now(timezone.utc).isoformat(), "tokens": tokens, "usd": usd, "tur": tur}]
                + d["son"])[:200]
    LEDGER_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return d


@app.get("/api/kullanim")
def get_kullanim() -> dict[str, Any]:
    d = ledger_oku()
    return {"cagri": d["cagri"], "input_tokens": d["input_tokens"], "usd": d["usd"], "son": d["son"][:20]}


# --------------------------------------------------------------------------- #
# Anlik degerlendirme: eklenti acik sayfayi gonderir, tek cagri ile karar doner
# --------------------------------------------------------------------------- #

class HizliIstek(BaseModel):
    model_config = {"extra": "allow"}

    baslik: str | None = None
    aciklama: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    konum_yolu: list[str] = Field(default_factory=list)
    fiyat_tl: float | None = None
    kategori: str = "emlak"
    hasar: dict[str, Any] | None = None
    kaydet: bool = False


@app.post("/api/degerlendir")
async def degerlendir(body: HizliIstek) -> dict[str, Any]:
    """Tek bir ilani tek cagri ile degerlendirir.

    Asamalarin sureleri ayri ayri olculur: kararin nasil olustugunu adim adim
    gosterebilmek icin uydurma degil gercek zamanlamalar gerekiyor.
    `kaydet` verilirse ilan, karariyla birlikte arsive de yazilir.
    """
    if not os.getenv("TYPESAFE_API_KEY"):
        raise HTTPException(status_code=400, detail="TYPESAFE_API_KEY tanımlı değil")

    p = profil_yukle()
    kriterler = analyzer.Kriterler(
        profil=p["profil"], oncelikler=p["oncelikler"], kirmizi_cizgiler=p["kirmizi_cizgiler"]
    )
    ilan = body.model_dump()
    kat = analyzer.kategori_coz(body.kategori)
    ekler = ekler_yukle()
    sorular = analyzer.sorular(kat, ekler)

    t_bas = time.perf_counter()
    state = analyzer.durum(ilan, kriterler)
    t_state = time.perf_counter()

    async with AsyncTypeSafeClient() as client:
        cevap = await client.system_one(state, sorular)
    t_yanit = time.perf_counter()

    karar = analyzer.karar_ver(cevap, kat, ekler, ilan)
    t_karar = time.perf_counter()

    ms = lambda a, b: round((b - a) * 1000, 1)  # noqa: E731
    olcum = analyzer.olcum(t_bas, cevap.usage)
    toplam = ledger_yaz(olcum["input_tokens"], olcum["usd"], "anlik")

    sonuc = {
        "sonuc": karar.sonuc,
        "skor": round(karar.skor, 4),
        "bayraklar": karar.bayraklar,
        "gerekce": karar.gerekce,
        "kapilar": karar.kapilar,
        "terimler": karar.terimler,
        "esikler": {
            "bayrak": analyzer.BAYRAK_ESIGI, "kararsiz_alt": analyzer.KARARSIZ_ALT,
            "skor": analyzer.SKOR_ESIGI, "guven": analyzer.GUVEN_ESIGI,
        },
        "olcum": olcum,
        "asamalar": {
            "state_ms": ms(t_bas, t_state),
            "model_ms": ms(t_state, t_yanit),
            "karar_ms": ms(t_yanit, t_karar),
        },
        "model": cevap.model,
        "kategori": kat,
        "soru_sayisi": len(cevap.answers),
        "toplam": {"cagri": toplam["cagri"], "usd": toplam["usd"], "input_tokens": toplam["input_tokens"]},
        "detay": {
            "nouls": {k: round(v.noul, 3) for k, v in cevap.nouls.items()},
            "scores": {
                k: {"skor": round(v.score, 2), "guven": round(v.confidence, 3),
                    "seviye": v.legend, "olasiliklar": {str(kk): round(vv, 3) for kk, vv in v.probabilities.items()}}
                for k, v in cevap.scores.items()
            },
            "choices": {
                k: {"secim": v.choice, "guven": round(v.confidence, 3),
                    "olasiliklar": {kk: round(vv, 3) for kk, vv in v.probabilities.items()}}
                for k, v in cevap.choices.items()
            },
        },
    }

    if body.kaydet:
        ham = body.model_dump()
        ham.pop("kaydet", None)
        ham["karar"] = {k: sonuc[k] for k in
                        ("sonuc", "skor", "bayraklar", "gerekce", "kapilar", "terimler",
                         "olcum", "asamalar", "model", "soru_sayisi", "detay", "esikler")}
        ham["karar"]["verildi"] = datetime.now(timezone.utc).isoformat()
        try:
            sonuc["arsiv"] = capture(Capture(**ham))
        except Exception as error:  # eksik alanla gelirse degerlendirme yine de donsun
            sonuc["arsiv_hatasi"] = str(error)

    return sonuc


@app.get("/api/ilan/{rid}")
def get_ilan(rid: str) -> dict[str, Any]:
    doc = load(SAFE_ID.sub("-", rid.lower()))
    if doc is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    return doc


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).resolve().parent / "ui.html").read_text(encoding="utf-8")


EKLENTI_DIR = Path(__file__).resolve().parent.parent / "extension"

# Panel, eklentiyle ayni akis kodunu kullanir; iki kopya tutulmuyor.
app.mount("/ext", StaticFiles(directory=EKLENTI_DIR), name="ext")


# --------------------------------------------------------------------------- #
# Oyun alani: serbest state + serbest sorular. Karar mantigi yok, ham cevap.
# --------------------------------------------------------------------------- #

class OyunIstek(BaseModel):
    state: Any                                  # duz metin ya da JSON nesnesi
    sorular: list[dict[str, Any]]


@app.post("/api/oyun")
async def oyun(body: OyunIstek) -> dict[str, Any]:
    """Verilen state ve sorulari oldugu gibi Jev'e sorar.

    Burada kirmizi bayrak, agirlik, esik yok: ne sorduysan onun ham cevabi.
    Modelin neyi yapip neyi yapamadigini gormek icin.
    """
    if not os.getenv("TYPESAFE_API_KEY"):
        raise HTTPException(status_code=400, detail="TYPESAFE_API_KEY tanımlı değil")
    if not body.sorular:
        raise HTTPException(status_code=400, detail="En az bir soru gerekli")

    sorular: dict[str, Any] = {}
    for i, e in enumerate(body.sorular):
        ad = (e.get("ad") or f"soru{i + 1}").strip()
        try:
            sorular[ad] = analyzer.ek_soruya_cevir(e)
        except (ValueError, TypeError) as hata:
            raise HTTPException(status_code=400, detail=f"{ad}: {hata}") from hata

    t0 = time.perf_counter()
    async with AsyncTypeSafeClient() as client:
        cevap = await client.system_one(body.state, sorular)
    olcum = analyzer.olcum(t0, cevap.usage)
    defter = ledger_yaz(olcum["input_tokens"], olcum["usd"], "oyun")

    cevaplar = {}
    for ad, a in cevap.nouls.items():
        cevaplar[ad] = {"tip": "noul", "deger": round(a.noul, 4)}
    for ad, a in cevap.choices.items():
        cevaplar[ad] = {
            "tip": "choice", "secim": a.choice, "guven": round(a.confidence, 4),
            "olasiliklar": {k: round(v, 4) for k, v in a.probabilities.items()},
        }
    for ad, a in cevap.scores.items():
        cevaplar[ad] = {
            "tip": "score", "skor": round(a.score, 3), "guven": round(a.confidence, 4),
            "seviye": {str(k): v for k, v in a.legend.items()},
            "olasiliklar": {str(k): round(v, 4) for k, v in a.probabilities.items()},
        }

    return {
        "cevaplar": cevaplar, "olcum": olcum, "model": cevap.model,
        "soru_sayisi": len(cevap.answers),
        "toplam": {"cagri": defter["cagri"], "usd": defter["usd"]},
    }


@app.get("/oyun", response_class=HTMLResponse)
def oyun_sayfasi() -> str:
    return (Path(__file__).resolve().parent / "oyun.html").read_text(encoding="utf-8")


@app.get("/yazarken", response_class=HTMLResponse)
def yazarken_sayfasi() -> str:
    return (Path(__file__).resolve().parent / "yazarken.html").read_text(encoding="utf-8")


@app.get("/macera", response_class=HTMLResponse)
def macera_sayfasi() -> str:
    return (Path(__file__).resolve().parent / "macera.html").read_text(encoding="utf-8")


@app.get("/akis/{rid}", response_class=HTMLResponse)
def akis(rid: str) -> str:
    """Arsivdeki bir ilanin kararini akis olarak oynatir.

    Gosterim kodu eklentiyle ayni dosyadan okunur (extension/akis.js); iki yerde
    ayri kopya tutulmuyor.
    """
    doc = load(SAFE_ID.sub("-", rid.lower()))
    if doc is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    karar = next((c.get("karar") for c in reversed(doc["captures"]) if c.get("karar")), None)
    if karar is None:
        raise HTTPException(status_code=404, detail="Bu ilanda kayitli bir karar yok — once degerlendir")

    baslik = doc["captures"][-1].get("baslik") or rid
    css = (EKLENTI_DIR / "akis.css").read_text(encoding="utf-8")
    js = (EKLENTI_DIR / "akis.js").read_text(encoding="utf-8")
    veri = json.dumps({"karar": karar, "baslik": baslik}, ensure_ascii=False)

    return f"""<!doctype html><html lang="tr"><meta charset="utf-8">
<title>Karar akışı — {baslik[:60]}</title>
<style>{css}</style>
<style>
 body{{margin:0;height:100vh;background:#dfe3e8;font:14px system-ui,-apple-system,"Segoe UI",sans-serif}}
 @media (prefers-color-scheme:dark){{body{{background:#0d0d0d}}}}
 .ac{{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);padding:12px 22px;
      border:0;border-radius:10px;background:#0b0b0b;color:#fff;font:inherit;font-weight:650;cursor:pointer}}
</style>
<body>
<button class="ac" id="ac">Karar akışını aç</button>
<script>{js}</script>
<script id="veri" type="application/json">{veri}</script>
<script>
 const D = JSON.parse(document.getElementById("veri").textContent);
 const ac = () => window.__ilanAkis.goster(D.karar, D.baslik);
 document.getElementById("ac").addEventListener("click", ac);
 ac();
</script>
</body></html>"""


# --------------------------------------------------------------------------- #
# Transkript analizi — YouTube eklentisi buraya gonderir
# --------------------------------------------------------------------------- #


class Cue(BaseModel):
    t: float
    metin: str


class TranskriptIstek(BaseModel):
    cue: list[Cue]
    dakika: float = 2.0
    eszamanlilik: int = 8
    video_id: str = ""
    baslik: str = ""


@app.post("/api/transkript/tahmin")
def transkript_tahmin(body: TranskriptIstek) -> dict[str, Any]:
    """Tek bir cagri yapmadan once maliyeti soyler. Saf kod."""
    if not body.cue:
        raise HTTPException(status_code=400, detail="cue listesi boş")
    return transkript.tahmin([c.model_dump() for c in body.cue], body.dakika)


@app.get("/api/transkript/sorular")
def transkript_sorulari() -> dict[str, Any]:
    """Sorulan 26 sorunun kendisi ve listelerin esikleri.

    "Neye gore karar verdi" sorusunun cevabi ikiye ayriliyor: hangi soru
    soruldu (burada) ve cevap hangi esige carpti (ESIKLER).
    """
    return transkript.soru_dokumu()


@app.post("/api/transkript")
async def transkript_analiz(body: TranskriptIstek) -> StreamingResponse:
    if not os.environ.get("TYPESAFE_API_KEY"):
        raise HTTPException(status_code=400, detail="TYPESAFE_API_KEY ayarlanmamış")
    if not body.cue:
        raise HTTPException(status_code=400, detail="cue listesi boş")

    async def akis() -> AsyncIterator[str]:
        async for s in transkript.analiz_akisi(
            [c.model_dump() for c in body.cue],
            body.dakika, max(1, min(body.eszamanlilik, 32)),
            body.video_id, body.baslik,
        ):
            # Maliyet defterini burada tutuyoruz: analiz modulu dosya bilmiyor.
            try:
                d = json.loads(s)
                if d.get("tip") == "bitti":
                    o = d["ozet"]
                    ledger_yaz(o["token"], o["usd"], "transkript")
            except (json.JSONDecodeError, KeyError):
                pass
            yield s

    return StreamingResponse(akis(), media_type="application/x-ndjson")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
