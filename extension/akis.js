// Kararin nasil olustugunu adim adim gosterir.
//
// DURUSTLUK NOTU: Jev 22 sorunun hepsini TEK cagrida, paralel cevaplar. Cevaplar
// tek tek gelmez; hepsi ayni anda doner. Bu yuzden asagidaki gosterimde sorular
// es zamanli dolar, sirayla degil. Kod tarafindaki karar mantigi ise gercekten
// sirali calisir, orasi adim adim gosterilebilir.
//
// Ust taraftaki "gercek zaman" cubugu olculmus sureleri gosterir. Alttaki
// gosterim, o surelerin icine sigmayacak kadar kisa adimlari izlenebilir hale
// getirmek icin uzatilir; bu yuzden ayri etiketlenir.

(() => {
  const HIZLAR = [
    { ad: "1x", carpan: 1, not: "gerçek hız" },
    { ad: "2x", carpan: 2, not: "2 kat yavaş" },
    { ad: "5x", carpan: 5, not: "5 kat yavaş" },
    { ad: "10x", carpan: 10, not: "10 kat yavaş — adım adım" },
  ];

  // Model bekleyisi gercek bir sure; yavaslatinca uzatmak bir sey ogretmez, sadece
  // bos ekrana baktirir. Carpani uygularken bir tavanla sinirlaniyor.
  const MODEL_TAVAN_MS = 2200;

  // Gosterim adimlarinin taban sureleri (ms). Model bekleyisi gercek olculen sure.
  const TABAN = { state: 70, cevap: 9, kapi: 45, terim: 60, final: 140 };

  const esc = (s) =>
    String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const yuzde = (v) => Math.max(0, Math.min(100, v * 100));

  const ETIKET = {
    kiracili_ima: "kiracılı mı?",
    celiskili_bilgi: "bilgiler çelişkili mi?",
    metin_yetersiz: "metin yetersiz mi?",
    tadilat_gerekli: "tadilat gerekli mi?",
    yatirimlik_dili: "yatırımcıya mı sesleniyor?",
    acil_satis_baskisi: "aciliyet baskısı var mı?",
    takas_arayisi: "takas arıyor mu?",
    abartili_pazarlama: "abartılı pazarlama mı?",
    iletisim_yonlendirme: "aramaya mı yönlendiriyor?",
    masraf_aliciya: "masraf alıcıda mı?",
    sifir_kullanilmamis: "sıfır mı?",
    manzara_iddiasi: "manzara iddiası var mı?",
    satici_dili: "satıcı dili",
    ilan_odagi: "ilanın odağı",
    hedef_kitle: "hedef kitle",
    teslim_durumu: "teslim durumu",
    profile_uygunluk: "profile uygunluk",
    ulasim_erisilebilirlik: "ulaşım erişilebilirliği",
    site_olanaklari: "site olanakları",
    konum_vaadi_somutlugu: "konum vaadinin somutluğu",
    bilgi_doygunlugu: "bilgi doygunluğu",
    satis_aciliyeti: "satış aciliyeti",
  };
  const ad = (k) => ETIKET[k] ?? k.replace(/_/g, " ");

  const ROZET = {
    kisa_liste: ["✓", "favoriye değer"],
    sana_sor: ["?", "emin değil"],
    ele: ["✕", "değmez"],
  };

  let iptal = null;

  function kapat() {
    if (iptal) iptal.durduruldu = true;
    document.getElementById("iy-akis")?.remove();
  }

  function goster(k, baslik) {
    kapat();
    const kat = document.createElement("div");
    kat.id = "iy-akis";
    kat.innerHTML = govde(k, baslik);
    document.body.appendChild(kat);

    kat.addEventListener("click", (e) => {
      if (e.target === kat || e.target.closest("[data-kapat]")) kapat();
    });

    const hizDugmeleri = kat.querySelectorAll("[data-hiz]");
    let secili = 2; // varsayilan 5x: adimlar izlenebilir ama bekleme uzamasin
    const isaretle = () =>
      hizDugmeleri.forEach((b, i) => b.classList.toggle("secili", i === secili));
    hizDugmeleri.forEach((b, i) =>
      b.addEventListener("click", () => {
        secili = i;
        isaretle();
        kat.querySelector("#iy-hiz-not").textContent = HIZLAR[i].not;
        oynat(kat, k, () => HIZLAR[secili].carpan);
      })
    );
    isaretle();
    kat.querySelector("#iy-hiz-not").textContent = HIZLAR[secili].not;
    kat.querySelector("[data-tekrar]").addEventListener("click", () =>
      oynat(kat, k, () => HIZLAR[secili].carpan)
    );

    oynat(kat, k, () => HIZLAR[secili].carpan);
  }

  // --- iskelet --------------------------------------------------------------
  function govde(k, baslik) {
    const a = k.asamalar;
    const toplam = a.state_ms + a.model_ms + a.karar_ms;
    const pay = (v) => Math.max(0.6, (v / toplam) * 100);
    const [ikon, etiket] = ROZET[k.sonuc] ?? ["", k.sonuc];

    const nouls = Object.keys(k.detay.nouls);
    const choices = Object.keys(k.detay.choices);
    const scores = Object.keys(k.detay.scores);
    const hepsi = [...nouls, ...choices, ...scores];

    return `
    <div class="iy-akis-kutu">
      <div class="iy-akis-bas">
        <div>
          <div class="iy-akis-baslik">Karar nasıl oluştu</div>
          <div class="iy-akis-alt">${esc((baslik ?? "").slice(0, 64))}</div>
        </div>
        <span class="iy-akis-rozet ${k.sonuc}">${ikon} ${etiket} · %${Math.round(k.skor * 100)}</span>
        <button class="iy-akis-x" data-kapat>×</button>
      </div>

      <div class="iy-akis-gercek">
        <div class="iy-akis-etiket">gerçek zaman · toplam ${toplam.toFixed(0)} ms</div>
        <div class="iy-zaman">
          <i class="z-state" style="width:${pay(a.state_ms)}%"></i>
          <i class="z-model" style="width:${pay(a.model_ms)}%"></i>
          <i class="z-karar" style="width:${pay(a.karar_ms)}%"></i>
        </div>
        <div class="iy-zaman-leg">
          <span><i class="sw z-state"></i>durum hazırlama ${a.state_ms} ms</span>
          <span><i class="sw z-model"></i>model + ağ ${a.model_ms} ms</span>
          <span><i class="sw z-karar"></i>kod kararı ${a.karar_ms} ms</span>
        </div>
      </div>

      <div class="iy-akis-kontrol">
        <button data-tekrar class="iy-akis-btn">↻ baştan</button>
        <span class="iy-akis-etiket">gösterim hızı</span>
        ${HIZLAR.map((h) => `<button data-hiz class="iy-akis-btn">${h.ad}</button>`).join("")}
        <span class="iy-akis-not" id="iy-hiz-not"></span>
      </div>

      <div class="iy-akis-govde">
        <section class="iy-adim" id="iy-a1">
          <h4><span class="iy-no">1</span> Durum hazırlanıyor</h4>
          <div class="iy-a1-icerik">
            <span class="iy-chip">başlık</span><span class="iy-chip">25 alan</span>
            <span class="iy-chip">açıklama</span><span class="iy-chip">konum yolu</span>
            <span class="iy-chip">alıcı profili</span>
            <span class="iy-chip iy-chip-say">${k.olcum.input_tokens} token</span>
          </div>
        </section>

        <section class="iy-adim" id="iy-a2">
          <h4><span class="iy-no">2</span> ${hepsi.length} soru <b>tek çağrıda</b>, paralel</h4>
          <div class="iy-akis-not">Hepsi aynı anda gider ve aynı anda döner — sırayla değil.
            22 soru için 22 değil tek istek atılır, gecikme tek çağrı kadardır.
            Maliyet yine de artar: her soru kendi metniyle ~100 token ekler.</div>
          <div class="iy-lanes">${hepsi.map((q) => `<span class="iy-lane" data-lane="${q}"><i></i>${esc(ad(q))}</span>`).join("")}</div>
        </section>

        <section class="iy-adim" id="iy-a3">
          <h4><span class="iy-no">3</span> Cevaplar</h4>
          <div class="iy-cevaplar">
            ${nouls.map((q) => noulSatir(q, k)).join("")}
            ${choices.map((q) => choiceSatir(q, k)).join("")}
            ${scores.map((q) => scoreSatir(q, k)).join("")}
          </div>
        </section>

        <section class="iy-adim" id="iy-a4">
          <h4><span class="iy-no">4</span> Kod karar veriyor</h4>
          <div class="iy-akis-not">Bu kısım modelde değil, kodda. Eşikler ve ağırlıklar senin.</div>
          <div class="iy-kapilar">${k.kapilar.map(kapiSatir).join("")}</div>
          <div class="iy-skor">
            <div class="iy-akis-etiket">ağırlıklı skor</div>
            <div class="iy-terimler">${k.terimler.map(terimSatir).join("")}</div>
            <div class="iy-toplam">
              <div class="iy-toplam-bar">
                <i id="iy-toplam-i" style="width:0"></i>
                <u style="left:${yuzde(k.esikler.skor)}%" title="eşik ${k.esikler.skor}"></u>
              </div>
              <b id="iy-toplam-v">0.00</b>
            </div>
            <div class="iy-akis-not">dikey çizgi: kısa liste eşiği ${k.esikler.skor}</div>
          </div>
          <div class="iy-final" id="iy-final"></div>
        </section>
      </div>
    </div>`;
  }

  function noulSatir(q, k) {
    const v = k.detay.nouls[q];
    return `<div class="iy-c" data-c="${q}">
      <div class="iy-c-ad">${esc(ad(q))}<span class="iy-c-tip">noul</span></div>
      <div class="iy-c-bar"><i style="width:0" data-fill="${yuzde(v)}"></i>
        <u style="left:${yuzde(k.esikler.bayrak)}%"></u></div>
      <b class="iy-c-v">${v.toFixed(2)}</b></div>`;
  }

  function choiceSatir(q, k) {
    const c = k.detay.choices[q];
    const siralı = Object.entries(c.olasiliklar).sort((a, b) => b[1] - a[1]);
    return `<div class="iy-c iy-c-blok" data-c="${q}">
      <div class="iy-c-ad">${esc(ad(q))}<span class="iy-c-tip">choice · güven ${c.guven.toFixed(2)}</span></div>
      <div class="iy-c-secenekler">${siralı
        .map(([o, p]) => `<div class="iy-o ${o === c.secim ? "sec" : ""}">
            <span>${esc(o)}</span>
            <div class="iy-o-bar"><i style="width:0" data-fill="${yuzde(p)}"></i></div>
            <b>${p.toFixed(2)}</b></div>`)
        .join("")}</div></div>`;
  }

  function scoreSatir(q, k) {
    const s = k.detay.scores[q];
    const enUst = Math.max(...Object.keys(s.seviye).map(Number));
    return `<div class="iy-c" data-c="${q}">
      <div class="iy-c-ad">${esc(ad(q))}<span class="iy-c-tip">score 0-${enUst} · güven ${s.guven.toFixed(2)}</span></div>
      <div class="iy-c-bar iy-c-score"><i style="width:0" data-fill="${yuzde(s.skor / enUst)}"></i></div>
      <b class="iy-c-v">${s.skor.toFixed(2)}</b></div>`;
  }

  function kapiSatir(g) {
    const yon = g.tur === "belirsizlik" || g.tur === "kararsiz" ? "belirsizlik" : "kırmızı bayrak";
    return `<div class="iy-kapi" data-kapi="${g.ad}-${g.tur}">
      <span class="iy-kapi-durum">·</span>
      <span class="iy-kapi-ad">${esc(g.etiket)}<small>${yon}</small></span>
      <span class="iy-kapi-deger">${g.deger.toFixed(2)} <small>tetik: ${esc(g.kosul ?? "> " + g.esik)}</small></span></div>`;
  }

  function terimSatir(t) {
    return `<div class="iy-terim" data-terim="${t.ad}">
      <span class="iy-terim-ad">${esc(ad(t.ad))}</span>
      <span class="iy-terim-hesap">${t.normalize.toFixed(2)} × ${t.agirlik} =
        <b>${t.katki.toFixed(3)}</b></span></div>`;
  }

  // --- oynatma --------------------------------------------------------------
  async function oynat(kat, k, carpan) {
    if (iptal) iptal.durduruldu = true;
    const benim = { durduruldu: false };
    iptal = benim;

    const bekle = (ms) =>
      new Promise((r) => setTimeout(r, Math.max(0, ms) * carpan()));
    const bitti = () => benim.durduruldu || !kat.isConnected;

    // sifirla
    kat.querySelectorAll(".iy-adim").forEach((s) => s.classList.remove("aktif", "gecti"));
    kat.querySelectorAll(".iy-lane").forEach((l) => l.classList.remove("dolu", "calisiyor"));
    kat.querySelectorAll("[data-fill]").forEach((i) => (i.style.width = "0"));
    kat.querySelectorAll(".iy-kapi").forEach((g) => g.classList.remove("acik", "kapali", "gorunur"));
    kat.querySelectorAll(".iy-terim").forEach((t) => t.classList.remove("gorunur"));
    kat.querySelector("#iy-toplam-i").style.width = "0";
    kat.querySelector("#iy-toplam-v").textContent = "0.00";
    kat.querySelector("#iy-final").innerHTML = "";

    const adim = (id) => {
      kat.querySelectorAll(".iy-adim").forEach((s) => {
        if (s.id === id) s.classList.add("aktif");
        else if (s.classList.contains("aktif")) s.classList.replace("aktif", "gecti");
      });
      kat.querySelector("#" + id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };

    // 1 — durum
    adim("iy-a1");
    await bekle(TABAN.state);
    if (bitti()) return;

    // 2 — sorular: hepsi AYNI ANDA. Sirayla yakmak yanlis olurdu.
    adim("iy-a2");
    const lanes = [...kat.querySelectorAll(".iy-lane")];
    lanes.forEach((l) => l.classList.add("calisiyor"));
    // Gercek olculen model + ag suresi, tavanla sinirli: yavaslatma adimlari
    // izlemek icin, bekleyisi uzatmak icin degil.
    await new Promise((r) =>
      setTimeout(r, Math.min(k.asamalar.model_ms * carpan(), MODEL_TAVAN_MS))
    );
    if (bitti()) return;
    lanes.forEach((l) => l.classList.replace("calisiyor", "dolu"));

    // 3 — cevaplar yerlerine otursun
    adim("iy-a3");
    for (const satir of kat.querySelectorAll(".iy-c")) {
      satir.querySelectorAll("[data-fill]").forEach((i) => (i.style.width = i.dataset.fill + "%"));
      satir.classList.add("gorunur");
      await bekle(TABAN.cevap);
      if (bitti()) return;
    }

    // 4 — kod kararı: burasi gercekten sirali calisir
    adim("iy-a4");
    for (const g of kat.querySelectorAll(".iy-kapi")) {
      g.classList.add("gorunur");
      const tetikledi = k.kapilar.find((x) => `${x.ad}-${x.tur}` === g.dataset.kapi)?.tetikledi;
      g.classList.add(tetikledi ? "acik" : "kapali");
      g.querySelector(".iy-kapi-durum").textContent = tetikledi ? "✕" : "✓";
      await bekle(TABAN.kapi);
      if (bitti()) return;
    }

    let birikim = 0;
    for (const t of k.terimler) {
      const el = kat.querySelector(`[data-terim="${t.ad}"]`);
      el?.classList.add("gorunur");
      birikim += t.katki;
      kat.querySelector("#iy-toplam-i").style.width = yuzde(birikim) + "%";
      kat.querySelector("#iy-toplam-v").textContent = birikim.toFixed(2);
      await bekle(TABAN.terim);
      if (bitti()) return;
    }

    await bekle(TABAN.final);
    if (bitti()) return;

    const [ikon, etiket] = ROZET[k.sonuc] ?? ["", k.sonuc];
    const neden = k.bayraklar.length
      ? `kırmızı bayrak açıldı: ${k.bayraklar.join(", ")} — skora bakılmadan elendi`
      : k.sonuc === "sana_sor"
      ? `belirsizlik kapısı açıldı: ${k.gerekce.join(", ")}`
      : birikim >= k.esikler.skor
      ? `hiçbir kapı açılmadı, skor ${birikim.toFixed(2)} ≥ eşik ${k.esikler.skor}`
      : `skor ${birikim.toFixed(2)} < eşik ${k.esikler.skor}`;

    kat.querySelector("#iy-final").innerHTML =
      `<div class="iy-final-rozet ${k.sonuc}">${ikon} ${etiket}</div>
       <div class="iy-final-neden">${esc(neden)}</div>`;
    kat.querySelector("#iy-final").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  window.__ilanAkis = { goster, kapat };
})();
