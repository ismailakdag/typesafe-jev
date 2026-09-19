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
from pydantic import BaseModel, Field
from typesafe_sdk import AsyncTypeSafeClient

from server import analyzer

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

    sorular = analyzer.sorular()
    semaphore = asyncio.Semaphore(max(1, req.eszamanlilik))
    jev_basla = time.perf_counter()

    async with AsyncTypeSafeClient() as client:
        async def degerlendir(ilan: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                t0 = time.perf_counter()
                try:
                    cevap = await client.system_one(analyzer.durum(ilan, kriterler), sorular)
                except Exception as error:  # ag, kota, dogrulama — ilani atlamak yerine bildir
                    return {"type": "karar_hata", "id": ilan["id"], "baslik": ilan["baslik"], "mesaj": str(error)}
                karar = analyzer.karar_ver(cevap)
                return {
                    "type": "karar",
                    "id": ilan["id"],
                    "sonuc": karar.sonuc,
                    "skor": round(karar.skor, 4),
                    "bayraklar": karar.bayraklar,
                    "gerekce": karar.gerekce,
                    "olcum": analyzer.olcum(t0, cevap.usage),
                    "model": cevap.model,
                    "detay": {
                        "nouls": {k: round(v.noul, 3) for k, v in cevap.nouls.items()},
                        "scores": {
                            k: {"skor": round(v.score, 2), "guven": round(v.confidence, 3), "seviye": v.legend}
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
            else:
                sayac["hata"] += 1
            yield line(sonuc)

    jev_ms = (time.perf_counter() - jev_basla) * 1000
    yield line({
        "type": "bitti",
        "ozet": {
            "kod_ms": round(kod_ms, 2),
            "jev_ms": round(jev_ms, 1),
            "toplam_ilan": len(ilanlar),
            "jev_gorulen": len(kalanlar),
            "input_tokens": toplam_token,
            "usd": round(toplam_usd, 8),
            **sayac,
        },
    })


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(analyze_stream(req), media_type="application/x-ndjson")


@app.get("/api/ilan/{rid}")
def get_ilan(rid: str) -> dict[str, Any]:
    doc = load(SAFE_ID.sub("-", rid.lower()))
    if doc is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    return doc


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).resolve().parent / "ui.html").read_text(encoding="utf-8")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
