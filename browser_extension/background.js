const DEFAULT_SERVER = "http://127.0.0.1:8080";

const MENU = [
  { id: "vg-add", title: "Přidat do fronty",             body: {} },
  { id: "vg-top", title: "Stáhnout jako další (nahoru)", body: { top: true } },
  { id: "vg-mp3", title: "Přidat jako MP3",              body: { audio_only: true } },
];

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "vg-root",
      title: "Video Grabber",
      contexts: ["link", "page", "video"],
    });
    for (const m of MENU) {
      chrome.contextMenus.create({
        id: m.id,
        parentId: "vg-root",
        title: m.title,
        contexts: ["link", "page", "video"],
      });
    }
  });
});

async function serverUrl() {
  const { server } = await chrome.storage.sync.get({ server: DEFAULT_SERVER });
  return (server || DEFAULT_SERVER).replace(/\/+$/, "");
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: chrome.runtime.getURL("icons/icon_48.png"),
    title,
    message,
  });
}

chrome.contextMenus.onClicked.addListener(async (info) => {
  const item = MENU.find((m) => m.id === info.menuItemId);
  if (!item) return;
  // a link wins; on a <video> or blank page area fall back to the page URL (blob: src is useless)
  const url = info.linkUrl || info.pageUrl;
  if (!url || !/^https?:/i.test(url)) {
    notify("Video Grabber", "Tohle nevypadá jako odkaz na video.");
    return;
  }

  const server = await serverUrl();
  try {
    const r = await fetch(server + "/api/add_bulk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: [url], ...item.body }),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const d = await r.json();
    if (d.added) {
      notify(item.body.top ? "Stáhne se jako další ✓" : "Přidáno do fronty ✓", url);
    } else if (d.moved) {
      notify("Posunuto nahoru ✓", "Odkaz už ve frontě byl: " + url);
    } else {
      notify("Už ve frontě", url);
    }
  } catch (e) {
    notify("Grabber neběží", "Nepodařilo se spojit s " + server + ". Spusť Video Grabber a zkus to znovu.");
  }
});

chrome.action.onClicked.addListener(async () => {
  chrome.tabs.create({ url: (await serverUrl()) + "/" });
});
