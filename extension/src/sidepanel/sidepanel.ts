interface MemoData {
  summary: string;
  entities: string[];
  tasks: string[];
  risks: string[];
  markdown: string;
  id?: string; // Add ID for editing
}

interface PageContext {
  url: string;
  title: string;
  main_text: string;
  selection: string;
  dom_map: any[];
  recent_events: any[];
}

class MemoSidePanel {
  private apiBaseUrl = 'http://localhost:8000/v1';
  private currentMemo: MemoData | null = null;
  private isLoading = false;
  private isEditing = false;

  constructor() {
    this.initializeUI();
    this.setupEventListeners();
  }

  private initializeUI() {
    document.body.innerHTML = `
      <div class="memo-container">
        <header class="memo-header">
          <h1>Memo</h1>
          <button id="createMemoBtn" class="primary-btn">Create Memo</button>
        </header>
        
        <div id="loadingState" class="loading-state hidden">
          <div class="spinner"></div>
          <p>Generating memo...</p>
        </div>
        
        <div id="memoContent" class="memo-content hidden">
          <div class="memo-section">
            <h3>Summary</h3>
            <p id="memoSummary"></p>
          </div>
          
          <div class="memo-section">
            <h3>Key Entities</h3>
            <div id="memoEntities" class="entity-list"></div>
          </div>
          
          <div class="memo-section">
            <h3>Next Steps</h3>
            <ol id="memoTasks"></ol>
          </div>
          
          <div class="memo-section">
            <h3>Risks & Considerations</h3>
            <ul id="memoRisks"></ul>
          </div>
          
          <div class="memo-actions">
            <button id="editMemoBtn" class="secondary-btn">Edit</button>
            <button id="saveMemoBtn" class="primary-btn">Save to Memory</button>
            <button id="updateMemoBtn" class="primary-btn hidden">Update</button>
            <button id="cancelEditBtn" class="secondary-btn hidden">Cancel</button>
            <button id="copyMemoBtn" class="secondary-btn">Copy Markdown</button>
          </div>
        </div>
        
        <div id="errorState" class="error-state hidden">
          <p id="errorMessage"></p>
          <button id="retryBtn" class="secondary-btn">Retry</button>
        </div>
        
        <div class="search-section">
          <h3>Search Memories</h3>
          <div class="search-input-group">
            <input type="text" id="searchInput" placeholder="Search past memos...">
            <button id="searchBtn">Search</button>
          </div>
          <div id="searchResults" class="search-results"></div>
        </div>
      </div>
    `;

    this.injectStyles();
  }

  private injectStyles() {
    const style = document.createElement('style');
    style.textContent = `
      * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }
      
      body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        font-size: 14px;
        line-height: 1.5;
        color: #333;
        background: #fff;
      }
      
      .memo-container {
        padding: 16px;
        max-width: 400px;
      }
      
      .memo-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 20px;
        padding-bottom: 16px;
        border-bottom: 1px solid #eee;
      }
      
      .memo-header h1 {
        font-size: 20px;
        font-weight: 600;
        color: #1a1a1a;
      }
      
      .primary-btn {
        background: #2563eb;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
        font-weight: 500;
      }
      
      .primary-btn:hover {
        background: #1d4ed8;
      }
      
      .secondary-btn {
        background: #f3f4f6;
        color: #374151;
        border: 1px solid #d1d5db;
        padding: 8px 16px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 13px;
      }
      
      .secondary-btn:hover {
        background: #e5e7eb;
      }
      
      .loading-state {
        text-align: center;
        padding: 40px 20px;
      }
      
      .spinner {
        width: 32px;
        height: 32px;
        border: 3px solid #f3f3f3;
        border-top: 3px solid #2563eb;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin: 0 auto 16px;
      }
      
      @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
      }
      
      .memo-content {
        margin-bottom: 24px;
      }
      
      .memo-section {
        margin-bottom: 20px;
      }
      
      .memo-section h3 {
        font-size: 16px;
        font-weight: 600;
        margin-bottom: 8px;
        color: #1a1a1a;
      }
      
      .entity-list {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      
      .entity-tag {
        background: #eff6ff;
        color: #1e40af;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        border: 1px solid #bfdbfe;
      }
      
      .memo-actions {
        display: flex;
        gap: 8px;
        margin-top: 16px;
      }
      
      .error-state {
        text-align: center;
        padding: 20px;
        color: #dc2626;
      }
      
      .search-section {
        border-top: 1px solid #eee;
        padding-top: 20px;
        margin-top: 20px;
      }
      
      .search-input-group {
        display: flex;
        gap: 8px;
        margin-bottom: 16px;
      }
      
      .search-input-group input {
        flex: 1;
        padding: 8px 12px;
        border: 1px solid #d1d5db;
        border-radius: 6px;
        font-size: 13px;
      }
      
      .search-results {
        max-height: 200px;
        overflow-y: auto;
      }
      
      .search-result-item {
        padding: 8px;
        border: 1px solid #e5e7eb;
        border-radius: 4px;
        margin-bottom: 8px;
        font-size: 12px;
      }
      
      .search-result-title {
        font-weight: 600;
        margin-bottom: 4px;
      }
      
      .search-result-text {
        color: #6b7280;
      }
      
      .hidden {
        display: none;
      }
    `;
    document.head.appendChild(style);
  }

  private setupEventListeners() {
    document.getElementById('createMemoBtn')?.addEventListener('click', () => {
      this.createMemo();
    });

    document.getElementById('saveMemoBtn')?.addEventListener('click', () => {
      this.saveMemo();
    });

    document.getElementById('copyMemoBtn')?.addEventListener('click', () => {
      this.copyMarkdown();
    });

    document.getElementById('editMemoBtn')?.addEventListener('click', () => {
      this.enterEditMode();
    });

    document.getElementById('updateMemoBtn')?.addEventListener('click', () => {
      this.updateMemo();
    });

    document.getElementById('cancelEditBtn')?.addEventListener('click', () => {
      this.cancelEdit();
    });

    document.getElementById('retryBtn')?.addEventListener('click', () => {
      this.createMemo();
    });

    document.getElementById('searchBtn')?.addEventListener('click', () => {
      this.searchMemories();
    });

    document.getElementById('searchInput')?.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.searchMemories();
      }
    });
  }

  private async createMemo() {
    if (this.isLoading) return;

    this.isLoading = true;
    this.showLoadingState();

    try {
      // Get page context from content script
      // Find the actual webpage tab (not the extension tab)
      const tabs = await chrome.tabs.query({ currentWindow: true });
      const webTab = tabs.find(tab => 
        tab.url && 
        !tab.url.startsWith('chrome-extension://') &&
        !tab.url.startsWith('chrome://') &&
        !tab.url.startsWith('about:')
      );
      
      if (!webTab || !webTab.id) {
        throw new Error('No web page found to create memo from');
      }
      
      console.log('Extracting context from tab:', webTab.url, 'Tab ID:', webTab.id);
      
      // Try to send message with error handling
      let context;
      try {
        context = await chrome.tabs.sendMessage(webTab.id, { action: 'extractContext' });
        console.log('Successfully got context:', context);
      } catch (error) {
        console.error('Failed to get context from content script:', error);
        // Inject content script if it's not loaded
        try {
          console.log('Attempting to inject content script...');
          await chrome.scripting.executeScript({
            target: { tabId: webTab.id },
            files: ['content.js']
          });
          
          // Wait a bit for script to load
          await new Promise(resolve => setTimeout(resolve, 500));
          
          // Try again
          context = await chrome.tabs.sendMessage(webTab.id, { action: 'extractContext' });
          console.log('Successfully got context after injection:', context);
        } catch (injectionError) {
          console.error('Failed to inject content script:', injectionError);
          // Fallback: create basic context from tab info
          context = {
            url: webTab.url,
            title: webTab.title || 'Untitled',
            main_text: `Page: ${webTab.title || webTab.url}`,
            selection: '',
            dom_map: [],
            recent_events: []
          };
          console.log('Using fallback context:', context);
        }
      }

      // Step 1: Compose context
      const composeResponse = await this.apiRequest('/compose', {
        method: 'POST',
        body: JSON.stringify(context)
      });

      // Step 2: Summarize
      const summarizeResponse = await this.apiRequest('/summarize', {
        method: 'POST',
        body: JSON.stringify({
          context_bundle: composeResponse.context_bundle,
          goal: 'Create a structured memo'
        })
      });

      this.currentMemo = summarizeResponse;
      this.displayMemo(summarizeResponse);

    } catch (error) {
      this.showError(error instanceof Error ? error.message : 'Failed to create memo');
    } finally {
      this.isLoading = false;
    }
  }

  private async saveMemo() {
    if (!this.currentMemo) return;

    try {
      // Find the actual webpage tab (not the extension tab)
      const tabs = await chrome.tabs.query({ currentWindow: true });
      const webTab = tabs.find(tab => 
        tab.url && 
        !tab.url.startsWith('chrome-extension://') &&
        !tab.url.startsWith('chrome://') &&
        !tab.url.startsWith('about:')
      );
      
      if (!webTab) {
        throw new Error('No web page found to save memo for');
      }
      
      await this.apiRequest('/memory/upsert', {
        method: 'POST',
        body: JSON.stringify({
          url: webTab.url,
          title: webTab.title,
          text: this.currentMemo.markdown,
          tags: this.currentMemo.entities.slice(0, 5),
          ts: Math.floor(Date.now() / 1000)
        })
      });

      // Show success feedback
      const saveBtn = document.getElementById('saveMemoBtn');
      if (saveBtn) {
        const originalText = saveBtn.textContent;
        saveBtn.textContent = 'Saved!';
        setTimeout(() => {
          saveBtn.textContent = originalText;
        }, 2000);
      }

    } catch (error) {
      this.showError('Failed to save memo');
    }
  }

  private copyMarkdown() {
    if (!this.currentMemo) return;

    navigator.clipboard.writeText(this.currentMemo.markdown).then(() => {
      const copyBtn = document.getElementById('copyMemoBtn');
      if (copyBtn) {
        const originalText = copyBtn.textContent;
        copyBtn.textContent = 'Copied!';
        setTimeout(() => {
          copyBtn.textContent = originalText;
        }, 2000);
      }
    });
  }

  private async searchMemories() {
    const searchInput = document.getElementById('searchInput') as HTMLInputElement;
    const query = searchInput.value.trim();
    
    if (!query) return;

    try {
      const results = await this.apiRequest(`/memory/search?q=${encodeURIComponent(query)}&k=5`);
      this.displaySearchResults(results.hits);
    } catch (error) {
      console.error('Search failed:', error);
    }
  }

  private async apiRequest(endpoint: string, options: RequestInit = {}) {
    const response = await fetch(`${this.apiBaseUrl}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      ...options
    });

    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }

    return response.json();
  }

  private showLoadingState() {
    document.getElementById('loadingState')?.classList.remove('hidden');
    document.getElementById('memoContent')?.classList.add('hidden');
    document.getElementById('errorState')?.classList.add('hidden');
  }

  private displayMemo(memo: MemoData) {
    document.getElementById('loadingState')?.classList.add('hidden');
    document.getElementById('errorState')?.classList.add('hidden');
    document.getElementById('memoContent')?.classList.remove('hidden');

    // Summary
    const summaryEl = document.getElementById('memoSummary');
    if (summaryEl) summaryEl.textContent = memo.summary;

    // Entities
    const entitiesEl = document.getElementById('memoEntities');
    if (entitiesEl) {
      entitiesEl.innerHTML = memo.entities
        .map(entity => `<span class="entity-tag">${entity}</span>`)
        .join('');
    }

    // Tasks
    const tasksEl = document.getElementById('memoTasks');
    if (tasksEl) {
      tasksEl.innerHTML = memo.tasks
        .map(task => `<li>${task}</li>`)
        .join('');
    }

    // Risks
    const risksEl = document.getElementById('memoRisks');
    if (risksEl) {
      risksEl.innerHTML = memo.risks
        .map(risk => `<li>${risk}</li>`)
        .join('');
    }
  }

  private showError(message: string) {
    document.getElementById('loadingState')?.classList.add('hidden');
    document.getElementById('memoContent')?.classList.add('hidden');
    document.getElementById('errorState')?.classList.remove('hidden');
    
    const errorEl = document.getElementById('errorMessage');
    if (errorEl) errorEl.textContent = message;
  }

  private displaySearchResults(results: any[]) {
    const resultsEl = document.getElementById('searchResults');
    if (!resultsEl) return;

    if (results.length === 0) {
      resultsEl.innerHTML = '<p>No memories found</p>';
      return;
    }

    resultsEl.innerHTML = results
      .map(result => `
        <div class="search-result-item">
          <div class="search-result-title">${result.text.substring(0, 100)}...</div>
          <div class="search-result-text">Similarity: ${(result.score * 100).toFixed(0)}%</div>
        </div>
      `)
      .join('');
  }

  private enterEditMode() {
    if (!this.currentMemo) return;
    
    this.isEditing = true;
    
    // Make content editable
    const summaryEl = document.getElementById('memoSummary') as HTMLElement;
    
    if (summaryEl) {
      summaryEl.contentEditable = 'true';
      summaryEl.style.border = '1px solid #ddd';
      summaryEl.style.padding = '8px';
      summaryEl.style.borderRadius = '4px';
      summaryEl.style.backgroundColor = '#f9f9f9';
    }
    
    // Convert lists to editable text areas for easier editing
    this.makeListEditable('memoEntities', this.currentMemo.entities);
    this.makeListEditable('memoTasks', this.currentMemo.tasks);
    this.makeListEditable('memoRisks', this.currentMemo.risks);
    
    // Toggle button visibility
    document.getElementById('editMemoBtn')?.classList.add('hidden');
    document.getElementById('updateMemoBtn')?.classList.remove('hidden');
    document.getElementById('cancelEditBtn')?.classList.remove('hidden');
  }

  private makeListEditable(containerId: string, items: string[]) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    const textarea = document.createElement('textarea');
    textarea.value = items.join('\n');
    textarea.style.width = '100%';
    textarea.style.minHeight = '80px';
    textarea.style.border = '1px solid #ddd';
    textarea.style.padding = '8px';
    textarea.style.borderRadius = '4px';
    textarea.style.fontFamily = 'inherit';
    textarea.style.backgroundColor = '#f9f9f9';
    textarea.dataset.originalType = containerId;
    
    container.innerHTML = '';
    container.appendChild(textarea);
  }

  private async updateMemo() {
    if (!this.currentMemo || !this.isEditing) return;

    try {
      // Collect edited content
      const summaryEl = document.getElementById('memoSummary') as HTMLElement;
      const entitiesEl = document.querySelector('#memoEntities textarea') as HTMLTextAreaElement;
      const tasksEl = document.querySelector('#memoTasks textarea') as HTMLTextAreaElement;
      const risksEl = document.querySelector('#memoRisks textarea') as HTMLTextAreaElement;

      const updatedMemo = {
        ...this.currentMemo,
        summary: summaryEl.textContent || this.currentMemo.summary,
        entities: entitiesEl ? entitiesEl.value.split('\n').filter(item => item.trim()) : this.currentMemo.entities,
        tasks: tasksEl ? tasksEl.value.split('\n').filter(item => item.trim()) : this.currentMemo.tasks,
        risks: risksEl ? risksEl.value.split('\n').filter(item => item.trim()) : this.currentMemo.risks
      };

      // Regenerate markdown
      updatedMemo.markdown = this.generateMarkdown(updatedMemo);
      
      this.currentMemo = updatedMemo;
      this.exitEditMode();
      this.displayMemo(this.currentMemo);
      
      console.log('Memo updated successfully');
      
    } catch (error) {
      console.error('Failed to update memo:', error);
      this.showError('Failed to update memo. Please try again.');
    }
  }

  private cancelEdit() {
    this.exitEditMode();
    if (this.currentMemo) {
      this.displayMemo(this.currentMemo);
    }
  }

  private exitEditMode() {
    this.isEditing = false;
    
    // Toggle button visibility
    document.getElementById('editMemoBtn')?.classList.remove('hidden');
    document.getElementById('updateMemoBtn')?.classList.add('hidden');
    document.getElementById('cancelEditBtn')?.classList.add('hidden');
  }

  private generateMarkdown(memo: MemoData): string {
    let markdown = '# Memo\n\n';
    
    if (memo.summary) {
      markdown += '## Summary\n';
      markdown += memo.summary + '\n\n';
    }
    
    if (memo.entities && memo.entities.length > 0) {
      markdown += '## Key Entities\n';
      memo.entities.forEach(entity => {
        markdown += `- ${entity}\n`;
      });
      markdown += '\n';
    }
    
    if (memo.tasks && memo.tasks.length > 0) {
      markdown += '## Next Steps\n';
      memo.tasks.forEach((task, index) => {
        markdown += `${index + 1}. ${task}\n`;
      });
      markdown += '\n';
    }
    
    if (memo.risks && memo.risks.length > 0) {
      markdown += '## Risks & Considerations\n';
      memo.risks.forEach(risk => {
        markdown += `- ${risk}\n`;
      });
      markdown += '\n';
    }
    
    return markdown;
  }

}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  new MemoSidePanel();
});