"""Yerel ilan arsivi.

Tarayici eklentisi yakaladigi kayitlari buraya gonderir. Sunucu sadece 127.0.0.1'e
baglanir; veri makineden disari cikmaz.

Calistir:  uv run python -m server.app
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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
        "capture_count": len(doc["captures"]),
        "first_seen": doc.get("first_seen"),
        "last_seen": doc.get("last_seen"),
        "extraction": latest.get("_extraction", {}),
    }


@app.get("/api/ilanlar")
def list_ilanlar() -> dict[str, Any]:
    docs = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            docs.append(summarize(json.loads(path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
    return {"count": len(docs), "ilanlar": docs}


@app.get("/api/ilan/{rid}")
def get_ilan(rid: str) -> dict[str, Any]:
    doc = load(SAFE_ID.sub("-", rid.lower()))
    if doc is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    return doc


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """<!doctype html><meta charset="utf-8">
<title>İlan Arşivi</title>
<style>
 body{font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif;margin:32px;max-width:900px;color:#16191d}
 h1{font-size:20px} table{border-collapse:collapse;width:100%;margin-top:16px}
 th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #e6e8ec;vertical-align:top}
 th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#5b616b}
 .muted{color:#5b616b} code{background:#f4f5f7;padding:1px 5px;border-radius:4px}
</style>
<h1>İlan Arşivi</h1>
<p class="muted">Eklenti buraya kayıt gönderiyor. Jev karşılaştırma arayüzü bir sonraki adımda.</p>
<div id="out">Yükleniyor…</div>
<script>
fetch('/api/ilanlar').then(r=>r.json()).then(d=>{
  if(!d.count){document.getElementById('out').innerHTML='<p class="muted">Henüz kayıt yok. Bir ilan sayfasında <b>Kaydet</b>\\'e bas.</p>';return}
  const rows=d.ilanlar.map(i=>`<tr>
    <td><a href="${i.url}" target="_blank" rel="noreferrer">${i.baslik??i.id}</a><br>
        <span class="muted">${(i.konum_yolu||[]).slice(-3).join(' / ')}</span></td>
    <td>${i.fiyat_tl?i.fiyat_tl.toLocaleString('tr-TR')+' TL':'<span class="muted">—</span>'}
        ${i.fiyat_degisti?'<br><span class="muted">fiyat değişti</span>':''}</td>
    <td>${i.fields.m2_brut??'—'} m²<br><span class="muted">${i.fields.oda_sayisi??''}</span></td>
    <td>${i.coords?`<code>${i.coords.lat.toFixed(5)}, ${i.coords.lon.toFixed(5)}</code><br><span class="muted">${i.coords.source}</span>`:'<span class="muted">konum yok</span>'}</td>
    <td class="muted">${i.capture_count} sürüm</td></tr>`).join('');
  document.getElementById('out').innerHTML=
    `<p>${d.count} ilan</p><table><tr><th>İlan</th><th>Fiyat</th><th>Alan</th><th>Konum</th><th></th></tr>${rows}</table>`;
});
</script>"""


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
