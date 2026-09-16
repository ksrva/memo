/**
 * Content script: reports what the reader has selected on the page.
 *
 * Deliberately passive — it injects no UI and stores nothing. The side panel
 * asks for the current selection when it needs it.
 */

interface PageContext {
  url: string;
  title: string;
  selection: string;
  excerpt: string;
}

const MAX_SELECTION = 4000;
const MAX_EXCERPT = 2000;

/** Best-effort main article text, for asking the backend what prior reading is relevant. */
function excerpt(): string {
  const candidate =
    document.querySelector('article') ??
    document.querySelector('main') ??
    document.querySelector('[role="main"]') ??
    document.body;

  const text = (candidate?.innerText ?? '').replace(/\s+/g, ' ').trim();
  return text.slice(0, MAX_EXCERPT);
}

function context(): PageContext {
  return {
    url: location.href,
    title: document.title,
    selection: (window.getSelection()?.toString() ?? '').trim().slice(0, MAX_SELECTION),
    excerpt: excerpt(),
  };
}

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (request?.action === 'getContext') {
    sendResponse(context());
  }
  return false;
});
