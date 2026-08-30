const apiUrl = document.getElementById('apiUrl');
const saved = document.getElementById('saved');

chrome.storage.local.get({ apiUrl: 'http://127.0.0.1:5002' }, (data) => {
  apiUrl.value = data.apiUrl;
});

document.getElementById('save').addEventListener('click', () => {
  const value = apiUrl.value.trim().replace(/\/$/, '');
  chrome.storage.local.set({ apiUrl: value }, () => {
    saved.textContent = 'Saved.';
  });
});
