// Arsive eklentiden erisim: acik sekmeyi yakala, kayitlari listele, detay ac, sil.

const SUNUCU = "http://127.0.0.1:8765";
const $ = (id) => document.getElementById(id);
const tl = (n) => (n == null ? "—" : n.toLocaleString("tr-TR") + " TL");
const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let kayitlar = [];
let acikDetay = null;
let aktifSekme = null;

function mesaj(text, cls = "") {
  $("msg").className = "msg " + cls;
  $("msg").textContent = text;
}

async function aktifSekmeyiAl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  aktifSekme = tab;
  const url = tab?.url ?? "";
  $("curl").textContent = tab?.title || url || "—";
  const yakalanabilir = /^https?:/.test(url);
  $("capture").disabled = !yakalanabilir;
  if (!yakalanabilir) {
    $("curlabel").textContent = "Bu sayfa yakalanamaz";
    $("capture").textContent = "Bu sayfa yakalanamaz";
  }
  return tab;
}

async function sunucuDurumu() {
  try {
    const d = await (await fetch(SUNUCU + "/api/ilanlar")).json();
    $("dot").className = "dot on";
    $("count").textContent = `${d.count} kayıt`;
    return d.ilanlar;
  } catch {
    $("dot").className = "dot off";
    $("count").textContent = "sunucu kapalı";
    $("list").innerHTML =
      '<div class="empty">Yerel arşiv sunucusuna ulaşılamıyor.<br><code>uv run python -m server.app</code></div>';
    return null;
  }
}

// --- yakalama -------------------------------------------------------------
$("capture").addEventListener("click", async () => {
  if (!aktifSekme?.id) return;
  $("capture").disabled = true;
  mesaj("Sayfa okunuyor…");
  try {
    await chrome.scripting.executeScript({ target: { tabId: aktifSekme.id }, files: ["extract.js"] });
    const [{ result: record }] = await chrome.scripting.executeScript({
      target: { tabId: aktifSekme.id },
      func: () => window.__ilanYakala.extract(),
    });
    const d = record._extraction;
    mesaj(`${d.pair_count} alan · ${d.photo_count} foto · konum: ${d.coords_source ?? "yok"} — gönderiliyor…`);
    const res = await fetch(SUNUCU + "/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const out = await res.json();
    const eksik = d.missing.length ? ` (eksik: ${d.missing.join(", ")})` : "";
    mesaj(`Kaydedildi — ${out.capture_count}. sürüm${eksik}`, "ok");
    await yenile();
  } catch (error) {
    mesaj("Olmadı: " + error.message, "err");
  } finally {
    $("capture").disabled = false;
  }
});

// --- liste ----------------------------------------------------------------
function satir(i) {
  const f = i.fields || {};
  const acik = acikDetay === i.id;
  const alanlar = Object.entries(f)
    .filter(([, v]) => v != null && v !== "")
    .map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${esc(v)}</td></tr>`)
    .join("");

  return `
  <div class="row" data-id="${i.id}">
    <div class="th" ${i.kapak ? `style="background-image:url('${esc(i.kapak)}')"` : ""}></div>
    <div class="info">
      <div class="n">${esc(i.baslik ?? i.id)}</div>
      <div class="m">${tl(i.fiyat_tl)}${i.fiyat_degisti ? ` · ilk ${tl(i.ilk_fiyat_tl)}` : ""}
        ${f.m2_brut ? ` · ${f.m2_brut} m²` : ""}${f.oda_sayisi ? ` · ${esc(f.oda_sayisi)}` : ""}</div>
      <div class="l">${esc((i.konum_yolu ?? []).slice(-3).join(" / "))}
        ${i.capture_count > 1 ? ` · ${i.capture_count} sürüm` : ""}</div>
    </div>
    <div class="acts">
      <button data-act="ac" data-url="${esc(i.url)}">aç</button>
      <button data-act="detay" data-id="${i.id}">${acik ? "kapat" : "detay"}</button>
      <button class="del" data-act="sil" data-id="${i.id}">sil</button>
    </div>
  </div>
  ${acik ? `<div class="det"><table>${alanlar}</table>
      ${i.coords ? `<div class="co">konum ${i.coords.lat.toFixed(5)}, ${i.coords.lon.toFixed(5)}
        (${esc(i.coords.source)})</div>` : '<div class="co">konum yok</div>'}
      <div class="co">${i.foto_sayisi ?? 0} foto · son görülme ${esc((i.last_seen ?? "").slice(0, 10))}</div>
      ${i.aciklama
        ? `<div class="dh">İlan açıklaması · ${i.aciklama.length} karakter</div>
           <div class="desc">${esc(i.aciklama)}</div>`
        : '<div class="co">açıklama yakalanamadı</div>'}
    </div>` : ""}`;
}

function ciz() {
  const q = $("q").value.trim().toLowerCase();
  const gosterilecek = q
    ? kayitlar.filter((i) =>
        `${i.baslik ?? ""} ${(i.konum_yolu ?? []).join(" ")} ${i.id}`.toLowerCase().includes(q)
      )
    : kayitlar;

  $("list").innerHTML = gosterilecek.length
    ? gosterilecek.map(satir).join("")
    : `<div class="empty">${kayitlar.length ? "Eşleşen kayıt yok." : "Arşiv boş. Bir ilan sayfasında Kaydet'e bas."}</div>`;
}

$("list").addEventListener("click", async (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  const { act, id, url } = btn.dataset;

  if (act === "ac") chrome.tabs.create({ url });
  else if (act === "detay") {
    acikDetay = acikDetay === id ? null : id;
    ciz();
  } else if (act === "sil") {
    const kayit = kayitlar.find((k) => k.id === id);
    if (!confirm(`Arşivden silinsin mi?\n\n${kayit?.baslik ?? id}`)) return;
    await fetch(`${SUNUCU}/api/ilan/${encodeURIComponent(id)}`, { method: "DELETE" });
    await yenile();
  }
});

$("q").addEventListener("input", ciz);
$("refresh").addEventListener("click", yenile);
$("openui").addEventListener("click", () => chrome.tabs.create({ url: SUNUCU }));

async function yenile() {
  const liste = await sunucuDurumu();
  if (!liste) return;
  kayitlar = liste;
  ciz();
}

aktifSekmeyiAl();
yenile();
