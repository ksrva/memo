interface DOMElement {
  role: string;
  text: string;
  selector: string;
}

interface UserEvent {
  type: string;
  text: string;
  ts: number;
}

class ContentExtractor {
  private recentEvents: UserEvent[] = [];
  private maxEvents = 10;

  constructor() {
    this.setupEventListeners();
  }

  private setupEventListeners() {
    // Track clicks on interactive elements
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      if (this.isInteractiveElement(target)) {
        this.addEvent({
          type: 'click',
          text: this.getElementText(target),
          ts: Date.now()
        });
      }
    });

    // Track text selections
    document.addEventListener('selectionchange', () => {
      const selection = window.getSelection();
      if (selection && selection.toString().length > 10) {
        this.addEvent({
          type: 'selection',
          text: selection.toString().substring(0, 100),
          ts: Date.now()
        });
      }
    });
  }

  private isInteractiveElement(element: HTMLElement): boolean {
    const interactiveTags = ['button', 'a', 'input', 'select', 'textarea'];
    const interactiveRoles = ['button', 'link', 'tab', 'menuitem'];
    
    return interactiveTags.includes(element.tagName.toLowerCase()) ||
           interactiveRoles.includes(element.getAttribute('role') || '') ||
           element.onclick !== null;
  }

  private getElementText(element: HTMLElement): string {
    return (element.textContent || element.getAttribute('aria-label') || 
            element.getAttribute('title') || '').trim().substring(0, 50);
  }

  private addEvent(event: UserEvent) {
    this.recentEvents.unshift(event);
    if (this.recentEvents.length > this.maxEvents) {
      this.recentEvents.pop();
    }
  }

  public extractPageContext(): {
    url: string;
    title: string;
    main_text: string;
    selection: string;
    dom_map: DOMElement[];
    recent_events: UserEvent[];
  } {
    return {
      url: window.location.href,
      title: document.title,
      main_text: this.getMainText(),
      selection: this.getCurrentSelection(),
      dom_map: this.buildDOMMap(),
      recent_events: this.recentEvents.slice()
    };
  }

  private getMainText(): string {
    // Remove script, style, and navigation elements
    const excludeSelectors = 'script, style, nav, header, footer, aside, .navigation, .sidebar, .ads';
    const excludeElements = document.querySelectorAll(excludeSelectors);
    
    // Clone document to avoid modifying original
    const clone = document.cloneNode(true) as Document;
    excludeElements.forEach((el, i) => {
      const cloneEl = clone.querySelectorAll(excludeSelectors)[i];
      if (cloneEl) cloneEl.remove();
    });

    // Extract text from main content areas
    const contentSelectors = [
      'main', 'article', '[role="main"]', '.content', '.post-content', 
      '.article-content', '.entry-content', '#content'
    ];

    for (const selector of contentSelectors) {
      const element = clone.querySelector(selector);
      if (element) {
        return this.cleanText(element.textContent || '');
      }
    }

    // Fallback to body text
    const bodyText = clone.body?.textContent || '';
    return this.cleanText(bodyText);
  }

  private cleanText(text: string): string {
    return text
      .replace(/\s+/g, ' ')  // Normalize whitespace
      .replace(/^\s+|\s+$/g, '')  // Trim
      .substring(0, 5000);  // Limit length
  }

  private getCurrentSelection(): string {
    const selection = window.getSelection();
    return selection ? selection.toString().trim() : '';
  }

  private buildDOMMap(): DOMElement[] {
    const domMap: DOMElement[] = [];
    const interactiveElements = document.querySelectorAll(
      'button, a[href], input, select, textarea, [role="button"], [role="link"], [onclick]'
    );

    interactiveElements.forEach((el, index) => {
      if (index < 20) {  // Limit to prevent large payloads
        const element = el as HTMLElement;
        domMap.push({
          role: this.getElementRole(element),
          text: this.getElementText(element),
          selector: this.generateSelector(element)
        });
      }
    });

    return domMap;
  }

  private getElementRole(element: HTMLElement): string {
    return element.getAttribute('role') || element.tagName.toLowerCase();
  }

  private generateSelector(element: HTMLElement): string {
    if (element.id) {
      return `#${element.id}`;
    }
    
    if (element.className) {
      const className = element.className.split(' ')[0];
      return `${element.tagName.toLowerCase()}.${className}`;
    }
    
    return element.tagName.toLowerCase();
  }
}

// Initialize content extractor
const extractor = new ContentExtractor();

// Listen for messages from popup/background
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractContext') {
    try {
      const context = extractor.extractPageContext();
      sendResponse(context);
    } catch (error) {
      console.error('Error extracting context:', error);
      sendResponse({ error: String(error) });
    }
    return true; // Indicates we will send a response asynchronously
  }
});

// Inject memo creation button (optional quick access)
function injectMemoButton() {
  if (document.getElementById('memo-quick-button')) return;
  
  const button = document.createElement('button');
  button.id = 'memo-quick-button';
  button.textContent = 'Create Memo';
  button.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    background: #2563eb;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  `;
  
  button.addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'openSidePanel' });
  });
  
  document.body.appendChild(button);
  
  // Auto-hide after 5 seconds
  setTimeout(() => {
    button.style.opacity = '0.3';
  }, 5000);
}

// Inject button on page load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', injectMemoButton);
} else {
  injectMemoButton();
}