/** Opens the side panel when the toolbar icon is clicked. */

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error('[memo] side panel setup failed', err));
});

// Let the panel know when the user moves to a different page, so it can refresh
// the passage and ask what prior reading is relevant here.
chrome.tabs.onActivated.addListener(() => {
  chrome.runtime.sendMessage({ action: 'tabChanged' }).catch(() => {});
});

chrome.tabs.onUpdated.addListener((_id, info) => {
  if (info.status === 'complete') {
    chrome.runtime.sendMessage({ action: 'tabChanged' }).catch(() => {});
  }
});
