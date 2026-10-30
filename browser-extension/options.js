const input = document.getElementById("server-url");
const saved = document.getElementById("saved");

chrome.storage.sync.get(["serverUrl"], ({ serverUrl }) => {
  if (serverUrl) input.value = serverUrl;
});

document.getElementById("save").addEventListener("click", () => {
  const value = input.value.trim().replace(/\/+$/, "");
  chrome.storage.sync.set({ serverUrl: value }, () => {
    saved.style.display = "block";
    setTimeout(() => { saved.style.display = "none"; }, 1500);
  });
});
