const DEFAULT_SERVER = "http://127.0.0.1:8080";
const input = document.getElementById("server");
const status = document.getElementById("status");

function clean(v) {
  return (v.trim() || DEFAULT_SERVER).replace(/\/+$/, "");
}

function show(msg, ok) {
  status.textContent = msg;
  status.style.color = ok ? "#22c55e" : "#e8336f";
}

chrome.storage.sync.get({ server: DEFAULT_SERVER }, ({ server }) => { input.value = server; });

// localhost is granted at install; any other host needs the user's OK (must run from a click)
async function ensurePermission(server) {
  const u = new URL(server);
  if (u.hostname === "127.0.0.1" || u.hostname === "localhost") return true;
  return chrome.permissions.request({ origins: [u.protocol + "//" + u.hostname + "/*"] });
}

document.getElementById("save").addEventListener("click", async () => {
  let server;
  try { server = clean(input.value); new URL(server); } catch { return show("Neplatná adresa", false); }
  if (!(await ensurePermission(server))) return show("Přístup k adrese nepovolen", false);
  await chrome.storage.sync.set({ server });
  input.value = server;
  show("Uloženo ✓", true);
});

document.getElementById("test").addEventListener("click", async () => {
  const server = clean(input.value);
  try {
    if (!(await ensurePermission(server))) return show("Přístup k adrese nepovolen", false);
    const r = await fetch(server + "/api/state");
    if (!r.ok) throw new Error();
    const d = await r.json();
    show("Spojeno ✓ (ve frontě " + (d.stats.queued + d.stats.pending) + ")", true);
  } catch {
    show("Grabber na " + server + " neodpovídá", false);
  }
});
