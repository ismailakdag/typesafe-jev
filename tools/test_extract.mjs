// Gercek bir kayitli sayfa uzerinde extract.js'i calistirir.
// Siteye hic dokunmadan cikarimi dogrulamak icin: node tools/test_extract.mjs <dosya.html> [url]

import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const file = process.argv[2] ?? "data/ornek/marka270.html";
const url =
  process.argv[3] ??
  "https://www.sahibinden.com/ilan/emlak-konut-satilik-marka-270-ultra-lux-sitede-3-plus1-arakat-sifir-bos-daireler-1299613994/detay/";

// Chrome'un kaydettigi dosya utf-8 olmayabilir; bozuk karakter sayisina gore sec.
const bytes = readFileSync(file);
const asUtf8 = new TextDecoder("utf-8").decode(bytes);
const asCp1254 = new TextDecoder("windows-1254").decode(bytes);
const bad = (s) => (s.match(/�/g) || []).length;
const html = bad(asUtf8) > bad(asCp1254) ? asCp1254 : asUtf8;
console.log(`kodlama: ${bad(asUtf8) > bad(asCp1254) ? "windows-1254" : "utf-8"} (utf8 hata=${bad(asUtf8)})\n`);

const dom = new JSDOM(html, { url, runScripts: "outside-only" });
const { window } = dom;

// jsdom innerText'i uygulamiyor; dogrulama icin textContent yeterli bir vekil.
Object.defineProperty(window.HTMLElement.prototype, "innerText", {
  get() {
    return this.textContent;
  },
  configurable: true,
});

window.eval(readFileSync("extension/extract.js", "utf-8"));
const record = window.__ilanYakala.extract();

console.log("--- teshis ---");
console.log(record._extraction);
console.log("\n--- eslesen alanlar ---");
console.log(record.fields);
console.log("\n--- temel ---");
console.log({
  baslik: record.baslik,
  fiyat_tl: record.fiyat_tl,
  ilan_no: record.ilan_no,
  coords: record.coords,
  konum_yolu: record.konum_yolu,
});
console.log("\n--- ozellikler (ilk 12 / " + record.ozellikler.length + ") ---");
console.log(record.ozellikler.slice(0, 12));
console.log("\n--- aciklama (ilk 300) ---");
console.log((record.aciklama ?? "").slice(0, 300));
console.log("\n--- eslenmemis etiket/deger ciftleri ---");
const mapped = new Set(Object.keys(record.fields));
const leftovers = Object.entries(record.raw_pairs).filter(([k]) => k.length < 40);
console.log(leftovers.slice(0, 30));
console.log(`\ntoplam cift: ${Object.keys(record.raw_pairs).length}, eslesen alan: ${mapped.size}`);
console.log(`foto: ${record.foto.length}, ham metin: ${record.raw_text.length} karakter`);

// --post ile kaydi yerel arsive gonderir: kayitli sayfadan gercek veriyle arayuzu test etmek icin.
if (process.argv.includes("--post")) {
  const res = await fetch("http://127.0.0.1:8765/capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  console.log("\narsive gonderildi:", await res.json());
}

// --degerlendir ile kaydi Jev'e gonderir ve karari yazdirir (arsive de kaydeder).
if (process.argv.includes("--degerlendir")) {
  const res = await fetch("http://127.0.0.1:8765/api/degerlendir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...record, kaydet: true }),
  });
  const y = await res.json();
  if (!res.ok) { console.log("\nHATA:", y); process.exit(1); }
  console.log(`\n=== ${y.kategori.toUpperCase()} · ${y.sonuc.toUpperCase()} · %${Math.round(y.skor*100)} ===`);
  console.log(`${y.soru_sayisi} soru · ${y.asamalar.model_ms} ms · ${y.olcum.input_tokens} token · $${y.olcum.usd.toFixed(7)}`);
  if (y.bayraklar.length) console.log("BAYRAK:", y.bayraklar.join(", "));
  console.log("gerekce:", y.gerekce.join(", "));
  console.log("\n--- noul ---");
  for (const [k, v] of Object.entries(y.detay.nouls)) console.log(`  ${k.padEnd(24)} ${v}`);
  console.log("--- choice ---");
  for (const [k, v] of Object.entries(y.detay.choices)) console.log(`  ${k.padEnd(24)} ${String(v.secim).padEnd(18)} guven ${v.guven}`);
  console.log("--- score ---");
  for (const [k, v] of Object.entries(y.detay.scores)) console.log(`  ${k.padEnd(24)} ${String(v.skor).padEnd(6)} guven ${v.guven}`);
}
