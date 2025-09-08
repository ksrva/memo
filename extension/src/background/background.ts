// Minimal test service worker
console.log('MEMO: Service worker loaded');

chrome.runtime.onInstalled.addListener(() => {
  console.log('MEMO: Extension installed');
});

chrome.action.onClicked.addListener((tab) => {
  console.log('MEMO: Icon clicked');
  chrome.tabs.create({ 
    url: chrome.runtime.getURL('sidepanel.html')
  });
});

// Handle messages from content script
chrome.runtime.onMessage.addListener((request, sender) => {
  console.log('Message received:', request);
  if (request.action === 'openSidePanel' && sender.tab) {
    // Trigger the action click handler
    chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel.html') });
  }
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'createMemo' && tab) {
    // Open sidepanel
    chrome.tabs.create({ url: chrome.runtime.getURL('sidepanel.html') });
  }
});