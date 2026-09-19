// Sayfadan yapilandirilmis kayit cikarir.
// Tasarim ilkesi: CSS sinif adlarina guvenme. Sayfanin SEKLINE bak (etiket/deger ciftleri,
// JSON-LD, meta etiketleri) ve her zaman ham metni de sakla; site HTML'ini degistirdiginde
// yapilandirilmis alanlar bozulsa bile veri kaybolmasin.

(() => {
  const TR = { latMin: 35.5, latMax: 42.5, lonMin: 25.0, lonMax: 45.0 };
  const clean = (s) => (s == null ? null : String(s).replace(/\s+/g, " ").trim() || null);
  const txt = (el) => clean(el && el.textContent);

  // "7.200.000 TL" -> 7200000 ; "120" -> 120 ; "6-10 arasi" -> 6 (ilk sayi)
  function trNumber(s) {
    if (!s) return null;
    const m = String(s).replace(/ /g, " ").match(/-?\d{1,3}(?:\.\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?/);
    if (!m) return null;
    const n = Number(m[0].replace(/\./g, "").replace(",", "."));
    return Number.isFinite(n) ? n : null;
  }

  // --- etiket/deger ciftleri -------------------------------------------------
  // sahibinden'in bilgi tablosu <li><strong>Etiket</strong><span>Deger</span></li> seklinde,
  // ama dt/dd ve th/td de yakalaniyor. Sinif adi kullanilmiyor: sekil eslesiyor.
  function labelValuePairs() {
    const pairs = {};
    const add = (k, v) => {
      k = clean(k);
      v = clean(v);
      if (!k || !v || k.length > 60 || v.length > 200) return;
      k = k.replace(/\s*:\s*$/, "");
      if (!(k in pairs)) pairs[k] = v;
    };
    document.querySelectorAll("li, div").forEach((el) => {
      if (el.children.length !== 2) return;
      const a = el.children[0];
      const b = el.children[1];
      if (a.children.length || b.children.length) return;
      add(a.textContent, b.textContent);
    });
    document.querySelectorAll("dl").forEach((dl) => {
      const kids = Array.from(dl.children);
      kids.forEach((el, i) => {
        if (el.tagName === "DT" && kids[i + 1] && kids[i + 1].tagName === "DD") {
          add(el.textContent, kids[i + 1].textContent);
        }
      });
    });
    document.querySelectorAll("tr").forEach((tr) => {
      if (tr.children.length === 2) add(tr.children[0].textContent, tr.children[1].textContent);
    });
    return pairs;
  }

  // --- konum -----------------------------------------------------------------
  function coordinates() {
    const ok = (lat, lon) =>
      Number.isFinite(lat) && Number.isFinite(lon) &&
      lat >= TR.latMin && lat <= TR.latMax && lon >= TR.lonMin && lon <= TR.lonMax;

    // 1) harita kabindaki data- nitelikleri
    for (const el of document.querySelectorAll("[data-lat], [data-latitude]")) {
      const lat = Number(el.getAttribute("data-lat") || el.getAttribute("data-latitude"));
      const lon = Number(
        el.getAttribute("data-lon") || el.getAttribute("data-lng") || el.getAttribute("data-longitude")
      );
      if (ok(lat, lon)) return { lat, lon, source: "data-attr" };
    }
    // 2) JSON-LD GeoCoordinates
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const blob = JSON.stringify(JSON.parse(s.textContent));
        const m = blob.match(/"latitude"\s*:\s*"?(-?\d+\.\d+)"?[^]{0,80}?"longitude"\s*:\s*"?(-?\d+\.\d+)"?/);
        if (m && ok(Number(m[1]), Number(m[2]))) return { lat: +m[1], lon: +m[2], source: "json-ld" };
      } catch (_) { /* bozuk ld+json, atla */ }
    }
    // 3) google maps iframe / statik harita URL'i
    for (const el of document.querySelectorAll("iframe[src], img[src]")) {
      const m = (el.src || "").match(/[?&](?:center|q|ll|markers)=(-?\d+\.\d+)(?:%2C|,)(-?\d+\.\d+)/);
      if (m && ok(Number(m[1]), Number(m[2]))) return { lat: +m[1], lon: +m[2], source: "maps-url" };
    }
    // 4) satir ici script'lerde lat/lon cifti (Turkiye sinirlariyla dogrulanmis)
    for (const s of document.querySelectorAll("script:not([src])")) {
      const body = s.textContent;
      if (!body || body.length > 400000) continue;
      const m = body.match(
        /["']?lat(?:itude)?["']?\s*[:=]\s*["']?(-?\d+\.\d{3,})["']?[^]{0,120}?["']?(?:lon|lng|longitude)["']?\s*[:=]\s*["']?(-?\d+\.\d{3,})["']?/i
      );
      if (m && ok(Number(m[1]), Number(m[2]))) return { lat: +m[1], lon: +m[2], source: "inline-script" };
    }
    return null;
  }

  // --- yardimcilar -----------------------------------------------------------
  function metaTags() {
    const out = {};
    document.querySelectorAll("meta[property], meta[name]").forEach((m) => {
      const k = m.getAttribute("property") || m.getAttribute("name");
      if (k && /^(og:|twitter:|description|keywords)/i.test(k) && m.content) out[k] = clean(m.content);
    });
    return out;
  }

  function jsonLd() {
    const out = [];
    document.querySelectorAll('script[type="application/ld+json"]').forEach((s) => {
      try { out.push(JSON.parse(s.textContent)); } catch (_) { /* atla */ }
    });
    return out;
  }

  function breadcrumb() {
    const nav = document.querySelector("[class*='readcrumb'], ol[class*='readcrumb'], nav[class*='readcrumb']");
    if (!nav) return [];
    return Array.from(nav.querySelectorAll("a, li")).map(txt).filter(Boolean).slice(0, 12);
  }

  function images(limit = 40) {
    const urls = new Set();
    document.querySelectorAll("img").forEach((img) => {
      const src = img.currentSrc || img.src || img.dataset.src || img.getAttribute("data-lazy");
      if (!src || !/^https?:/.test(src)) return;
      if (/sprite|icon|logo|placeholder|blank|\.svg($|\?)/i.test(src)) return;
      const w = img.naturalWidth || Number(img.getAttribute("width")) || 0;
      if (w && w < 120) return;
      urls.add(src.split("?")[0]);
    });
    return Array.from(urls).slice(0, limit);
  }

  // Sayfadaki en buyuk yaprak metin blogu: aciklama alani genelde budur.
  function longestTextBlock() {
    let best = null;
    let bestLen = 0;
    document.querySelectorAll("div, section, article, p").forEach((el) => {
      if (el.querySelector("div, section, article")) return;
      const t = el.innerText || "";
      if (t.length > bestLen && t.length < 20000) {
        best = el;
        bestLen = t.length;
      }
    });
    return best ? clean(best.innerText) : null;
  }

  function selectedFeatures() {
    const picked = Array.from(document.querySelectorAll("li.selected, li[class*='selected'], span.selected"))
      .map(txt)
      .filter(Boolean);
    return Array.from(new Set(picked)).slice(0, 200);
  }

  // --- sahibinden ilan sayfasi ----------------------------------------------
  const SAHIBINDEN_ID = /-(\d{7,})\/detay/;

  function isSahibindenListing() {
    return location.hostname.endsWith("sahibinden.com") && SAHIBINDEN_ID.test(location.pathname);
  }

  // Turkce etiketleri kodda kullanilabilir alan adlarina cevirir.
  const FIELD_MAP = {
    "İlan No": ["ilan_no", "text"],
    "İlan Tarihi": ["ilan_tarihi", "text"],
    "Emlak Tipi": ["emlak_tipi", "text"],
    "m² (Brüt)": ["m2_brut", "num"],
    "m² (Net)": ["m2_net", "num"],
    "Oda Sayısı": ["oda_sayisi", "text"],
    "Bina Yaşı": ["bina_yasi", "text"],
    "Kat Sayısı": ["kat_sayisi", "num"],
    "Bulunduğu Kat": ["bulundugu_kat", "text"],
    "Isıtma": ["isitma", "text"],
    "Banyo Sayısı": ["banyo_sayisi", "num"],
    "Mutfak": ["mutfak", "text"],
    "Balkon": ["balkon", "text"],
    "Asansör": ["asansor", "text"],
    "Otopark": ["otopark", "text"],
    "Eşyalı": ["esyali", "text"],
    "Kullanım Durumu": ["kullanim_durumu", "text"],
    "Site İçerisinde": ["site_icerisinde", "text"],
    "Site Adı": ["site_adi", "text"],
    "Aidat (TL)": ["aidat_tl", "num"],
    "Krediye Uygun": ["krediye_uygun", "text"],
    "Tapu Durumu": ["tapu_durumu", "text"],
    "Kimden": ["kimden", "text"],
    "Takas": ["takas", "text"],
    "Enerji Kimlik Belgesi": ["enerji_belgesi", "text"],
    // otomotiv tarafi
    "Yıl": ["yil", "num"],
    "Kilometre": ["km", "num"],
    "Vites": ["vites", "text"],
    "Yakıt": ["yakit", "text"],
    "Marka": ["marka", "text"],
    "Seri": ["seri", "text"],
    "Model": ["model", "text"],
    "Motor Gücü": ["motor_gucu", "text"],
    "Ağır Hasar Kayıtlı": ["agir_hasar", "text"],
    "Renk": ["renk", "text"],
  };

  function normalizeFields(pairs) {
    const fields = {};
    Object.entries(FIELD_MAP).forEach(([label, spec]) => {
      if (pairs[label] == null) return;
      fields[spec[0]] = spec[1] === "num" ? trNumber(pairs[label]) : pairs[label];
    });
    return fields;
  }

  function priceTL(pairs) {
    // Once bilgi tablosunda ara, sonra sayfadaki en buyuk "... TL" degerini al.
    for (const [k, v] of Object.entries(pairs)) {
      if (/fiyat/i.test(k) && /TL/i.test(v)) return trNumber(v);
    }
    let best = null;
    document.querySelectorAll("h1, h2, h3, div, span").forEach((el) => {
      if (el.children.length) return;
      const t = el.textContent || "";
      if (!/\bTL\b/.test(t) || t.length > 40) return;
      const n = trNumber(t);
      if (n && n > 1000 && (best === null || n > best)) best = n;
    });
    return best;
  }

  function extract() {
    const pairs = labelValuePairs();
    const sahibinden = isSahibindenListing();
    const record = {
      site: location.hostname.replace(/^www\./, ""),
      url: location.href.split("?")[0],
      captured_at: new Date().toISOString(),
      page_kind: sahibinden ? "sahibinden_ilan" : "genel",
      ilan_no: sahibinden ? (location.pathname.match(SAHIBINDEN_ID) || [])[1] : null,
      baslik: txt(document.querySelector("h1")) || clean(document.title),
      fiyat_tl: priceTL(pairs),
      konum_yolu: breadcrumb(),
      coords: coordinates(),
      fields: normalizeFields(pairs),
      raw_pairs: pairs,
      ozellikler: selectedFeatures(),
      aciklama: longestTextBlock(),
      foto: images(),
      meta: metaTags(),
      json_ld: jsonLd(),
      raw_text: (clean(document.body.innerText) || "").slice(0, 60000),
    };
    record.ilan_no = record.ilan_no || record.fields.ilan_no || null;
    record._extraction = {
      pair_count: Object.keys(pairs).length,
      mapped_field_count: Object.keys(record.fields).length,
      coords_source: record.coords ? record.coords.source : null,
      photo_count: record.foto.length,
      feature_count: record.ozellikler.length,
      missing: ["fiyat_tl", "baslik", "coords", "aciklama"].filter((k) => !record[k]),
    };
    return record;
  }

  window.__ilanYakala = { extract, isSahibindenListing };
})();
