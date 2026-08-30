const statusEl = document.getElementById('status');

document.getElementById('openOptions').addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});

document.getElementById('capture').addEventListener('click', async () => {
  statusEl.textContent = 'Capturing opened email...';
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error('No active tab found.');
    const response = await chrome.tabs.sendMessage(tab.id, { type: 'CAPTURE_EMAIL' });
    if (!response?.ok) throw new Error(response?.error || 'Could not capture email.');
    statusEl.textContent = `Captured ${response.subject ? '"' + response.subject.slice(0, 45) + '"' : 'email'}.`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
});
