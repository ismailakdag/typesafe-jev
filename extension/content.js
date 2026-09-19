// Ilan sayfasi taninirsa kose panelini gosterir. Hicbir sey otomatik gonderilmez:
// her kayit tek bir tikla, senin istegin uzerine olur.

(() => {
  if (window.__ilanYakalaPanel) return;
  window.__ilanYakalaPanel = true;

  const api = window.__ilanYakala;
  if (!api || !api.isSahibindenListing()) return;

  const panel = document.createElement("div");
  panel.id = "iy-panel";
  panel.innerHTML = `
    <div class="iy-title">Bu ilanı arşivine kaydedeyim mi?</div>
    <div class="iy-sub" id="iy-sub">Sayfadaki tüm alanlar, konum ve açıklama alınır.</div>
    <div class="iy-row">
      <button id="iy-save" class="iy-btn iy-primary">Kaydet</button>
      <button id="iy-close" class="iy-btn">Kapat</button>
    </div>`;
  document.body.appendChild(panel);

  const sub = panel.querySelector("#iy-sub");
  const saveBtn = panel.querySelector("#iy-save");

  panel.querySelector("#iy-close").addEventListener("click", () => panel.remove());

  saveBtn.addEventListener("click", () => {
    saveBtn.disabled = true;
    sub.textContent = "Okunuyor…";
    let record;
    try {
      record = api.extract();
    } catch (error) {
      sub.textContent = "Okuma hatası: " + error.message;
      saveBtn.disabled = false;
      return;
    }

    const d = record._extraction;
    sub.textContent = `${d.pair_count} alan · ${d.photo_count} foto · konum: ${d.coords_source || "yok"} — gönderiliyor…`;

    chrome.runtime.sendMessage({ type: "capture", record }, (response) => {
      saveBtn.disabled = false;
      if (chrome.runtime.lastError) {
        sub.textContent = "Eklenti hatası: " + chrome.runtime.lastError.message;
        return;
      }
      if (!response || !response.ok) {
        sub.textContent = "Sunucuya ulaşılamadı. `uv run python -m server.app` çalışıyor mu?";
        panel.classList.add("iy-error");
        return;
      }
      panel.classList.add("iy-done");
      const eksik = d.missing.length ? ` (eksik: ${d.missing.join(", ")})` : "";
      sub.textContent = `Kaydedildi — ${response.id}, ${response.capture_count}. sürüm${eksik}`;
      saveBtn.textContent = "Tekrar kaydet";
    });
  });
})();
