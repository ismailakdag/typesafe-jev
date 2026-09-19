// Icerik betiginin yerel sunucuyla konusma koprusu.
// Istekler burada atilir cunku icerik betiginden yapilan capraz kaynak istekleri
// sayfanin CORS kurallarina takilir; servis calisani host izinleriyle calisir.
// Veri sadece 127.0.0.1'e gider; baska hicbir yere istek atilmaz.

const SUNUCU = "http://127.0.0.1:8765";

const UCLAR = {
  capture: "/capture",
  degerlendir: "/api/degerlendir",
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const yol = UCLAR[message.type];
  if (!yol) return;

  fetch(SUNUCU + yol, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message.record),
  })
    .then(async (response) => {
      const govde = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(govde.detail || "HTTP " + response.status);
      }
      sendResponse({ ok: true, ...govde });
    })
    .catch((error) => sendResponse({ ok: false, error: error.message }));

  return true; // yanit asenkron
});
