// Ilan sayfasi taninirsa kose panelini gosterir.
// Hicbir sey kendiliginden gonderilmez: degerlendirme de kayit da tek tikla,
// senin istegin uzerine olur. Otomatik degerlendirme kapali gelir ve acilsa bile
// ayni ilan icin sayfa basina bir kez calisir — habersiz kredi harcamasin.

(() => {
  if (window.__ilanYakalaPanel) return;
  window.__ilanYakalaPanel = true;

  const api = window.__ilanYakala;
  if (!api || !api.isSahibindenListing()) return;

  const ROZET = {
    kisa_liste: ["✓", "favoriye değer", "iy-ok"],
    sana_sor: ["?", "emin değil", "iy-warn"],
    ele: ["✕", "değmez", "iy-bad"],
  };

  const panel = document.createElement("div");
  panel.id = "iy-panel";
  panel.innerHTML = `
    <div class="iy-head">
      <span class="iy-title">İlan Yakala</span>
      <button class="iy-x" id="iy-close" title="Kapat">×</button>
    </div>
    <div class="iy-sub" id="iy-sub">Bu ilanı değerlendireyim mi?</div>
    <div id="iy-result"></div>
    <div class="iy-row">
      <button id="iy-eval" class="iy-btn iy-primary">Değerlendir</button>
      <button id="iy-save" class="iy-btn">Arşive kaydet</button>
    </div>
    <label class="iy-auto"><input type="checkbox" id="iy-oto"> Açtığım her ilanı otomatik değerlendir</label>
    <div class="iy-ledger" id="iy-ledger"></div>`;
  document.body.appendChild(panel);

  const $ = (id) => panel.querySelector("#" + id);
  const sub = $("iy-sub");
  const sonuc = $("iy-result");
  const defter = $("iy-ledger");

  $("iy-close").addEventListener("click", () => panel.remove());

  const oku = () => {
    try {
      return api.extract();
    } catch (error) {
      sub.textContent = "Sayfa okunamadı: " + error.message;
      return null;
    }
  };

  const gonder = (type, record) =>
    new Promise((resolve) => {
      chrome.runtime.sendMessage({ type, record }, (yanit) => {
        if (chrome.runtime.lastError) resolve({ ok: false, error: chrome.runtime.lastError.message });
        else resolve(yanit ?? { ok: false, error: "Sunucuya ulaşılamadı" });
      });
    });

  // --- anlik degerlendirme -------------------------------------------------
  let calisiyor = false;
  let sonKarar = null;  // arsive kaydederken ilistirilir, akis gosteriminde kullanilir

  async function degerlendir() {
    if (calisiyor) return;
    calisiyor = true;
    const btn = $("iy-eval");
    btn.disabled = true;
    panel.classList.remove("iy-ok", "iy-warn", "iy-bad");
    sonuc.innerHTML = "";
    sub.textContent = "Jev'e soruluyor…";

    const record = oku();
    if (!record) { btn.disabled = false; calisiyor = false; return; }

    const t0 = performance.now();
    const y = await gonder("degerlendir", record);
    const gidisDonus = Math.round(performance.now() - t0);

    btn.disabled = false;
    calisiyor = false;

    if (!y.ok) {
      panel.classList.add("iy-bad");
      sub.textContent = "Olmadı: " + y.error;
      return;
    }

    sonKarar = y;
    const [ikon, etiket, sinif] = ROZET[y.sonuc] ?? ["", y.sonuc, ""];
    panel.classList.add(sinif);
    sub.textContent = `${record._extraction.pair_count} alan okundu · ${y.soru_sayisi} soru tek çağrıda`;

    const etiketler = [
      ...y.bayraklar.map((b) => `<span class="iy-tag iy-tag-bad">⚑ ${b}</span>`),
      ...y.gerekce.map((g) => `<span class="iy-tag">${g}</span>`),
    ].join("");

    sonuc.innerHTML = `
      <div class="iy-verdict ${sinif}"><span class="iy-icon">${ikon}</span>
        <span>${etiket}</span><b>${Math.round(y.skor * 100)}%</b></div>
      <div class="iy-bar"><i style="width:${Math.round(y.skor * 100)}%"></i></div>
      <div class="iy-tags">${etiketler}</div>
      <div class="iy-cost">
        <span>${y.olcum.ms} ms<small> (ağ dahil ${gidisDonus})</small></span>
        <span>${y.olcum.input_tokens} token</span>
        <span class="iy-usd">$${y.olcum.usd.toFixed(7)}</span>
      </div>
      <button id="iy-akis-ac" class="iy-btn iy-genis">Nasıl karar verdi? ▸</button>`;

    sonuc.querySelector("#iy-akis-ac").addEventListener("click", () =>
      window.__ilanAkis.goster(y, record.baslik)
    );

    const t = y.toplam;
    const binTane = (t.usd / Math.max(t.cagri, 1)) * 1000;
    defter.textContent =
      `bu makinede toplam ${t.cagri} çağrı · $${t.usd.toFixed(6)} — bu hızla 1000 ilan ≈ $${binTane.toFixed(3)}`;
  }

  $("iy-eval").addEventListener("click", degerlendir);

  // --- arsive kaydet -------------------------------------------------------
  $("iy-save").addEventListener("click", async () => {
    const btn = $("iy-save");
    btn.disabled = true;
    const record = oku();
    if (!record) { btn.disabled = false; return; }
    const d = record._extraction;
    if (sonKarar) record.karar = { ...sonKarar, verildi: new Date().toISOString() };
    sub.textContent = `${d.pair_count} alan · ${d.photo_count} foto`
      + `${sonKarar ? " · karar da kaydediliyor" : ""} …`;
    const y = await gonder("capture", record);
    btn.disabled = false;
    if (!y.ok) {
      sub.textContent = "Kaydedilemedi: " + y.error;
      return;
    }
    const eksik = d.missing.length ? ` (eksik: ${d.missing.join(", ")})` : "";
    sub.textContent = `Arşive kaydedildi — ${y.capture_count}. sürüm`
      + `${sonKarar ? " (kararıyla birlikte)" : ""}${eksik}`;
    btn.textContent = "Tekrar kaydet";
  });

  // --- otomatik degerlendirme ----------------------------------------------
  const OTO = "iy_oto_degerlendir";
  chrome.storage.sync.get(OTO, (d) => {
    const acik = Boolean(d[OTO]);
    $("iy-oto").checked = acik;
    if (acik) degerlendir();
  });
  $("iy-oto").addEventListener("change", (e) => {
    chrome.storage.sync.set({ [OTO]: e.target.checked });
    if (e.target.checked) degerlendir();
  });
})();
