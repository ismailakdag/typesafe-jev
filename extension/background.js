// Icerik betiginden gelen kayitlari yerel arsiv sunucusuna iletir.
// Veri sadece 127.0.0.1'e gider; baska hicbir yere istek atilmaz.
//
// (Arac cubugu dugmesi artik popup aciyor, bu yuzden action.onClicked yok:
//  genel modda yakalama popup.js icinde.)

const ENDPOINT = "http://127.0.0.1:8765/capture";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "capture") return;
  fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(message.record),
  })
    .then(async (response) => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      sendResponse({ ok: true, ...(await response.json()) });
    })
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true; // yanit asenkron
});
