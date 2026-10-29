// Opens a new tab at {your server}/app/jobs/add?url=<this page's link>. That page (already part of the
// StillOpen app) reads the link itself via the signed-in session already open in your browser -- this
// extension never sends the page content anywhere, it only ever opens one URL.
const readyEl = document.getElementById("ready");
const setupEl = document.getElementById("setup");
const statusEl = document.getElementById("status");
const addButton = document.getElementById("add");

function normalizeBase(url) {
  return (url || "").trim().replace(/\/+$/, "");
}

chrome.storage.sync.get(["serverUrl"], ({ serverUrl }) => {
  const base = normalizeBase(serverUrl);
  if (!base) {
    readyEl.style.display = "none";
    setupEl.style.display = "block";
    return;
  }

  addButton.addEventListener("click", async () => {
    addButton.disabled = true;
    statusEl.textContent = "";
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab || !tab.url || !/^https?:\/\//.test(tab.url)) {
        statusEl.textContent = "This page doesn't look like a job posting link.";
        addButton.disabled = false;
        return;
      }
      const target = `${base}/app/jobs/add?url=${encodeURIComponent(tab.url)}`;
      await chrome.tabs.create({ url: target });
      window.close();
    } catch (err) {
      statusEl.textContent = "Could not open StillOpen. Check your server address in settings.";
      addButton.disabled = false;
    }
  });
});

document.getElementById("open-options").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});
