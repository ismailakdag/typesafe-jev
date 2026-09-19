// Kayitlari yerel arsiv sunucusuna iletir. Veri sadece 127.0.0.1'e gider.

const ENDPOINT = "http://127.0.0.1:8765/capture";

async function send(record) {
  const response = await fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(record),
  });
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response.json();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type !== "capture") return;
  send(message.record)
    .then((data) => sendResponse({ ok: true, ...data }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true; // yanit asenkron
});

// Araç çubuğu düğmesi: tanınmayan sayfalarda da genel modda yakala.
chrome.action.onClicked.addListener(async (tab) => {
  if (!tab.id) return;
  const [injection] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    files: ["extract.js"],
  });
  void injection;
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.__ilanYakala.extract(),
  });
  try {
    const data = await send(result.result);
    await chrome.action.setBadgeText({ tabId: tab.id, text: "OK" });
    void data;
  } catch (error) {
    await chrome.action.setBadgeText({ tabId: tab.id, text: "HATA" });
    console.error("Ilan Yakala:", error);
  }
  setTimeout(() => chrome.action.setBadgeText({ tabId: tab.id, text: "" }), 4000);
});
