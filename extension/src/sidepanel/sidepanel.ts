/**
 * Side panel.
 *
 * Markup lives in sidepanel.html; this file only fills it with data, always via
 * textContent or the `el()` builder. No template-literal HTML anywhere.
 */

import { api, ApiError, Link, Note, SearchHit } from '../shared/api';
import { $, clear, el, relative, safeLink, show } from '../shared/dom';

interface PageContext {
  url: string;
  title: string;
  selection: string;
  excerpt: string;
}

const RELATION_LABEL: Record<Link['relation'], string> = {
  agrees: 'agrees',
  contradicts: 'contradicts',
  extends: 'extends',
  example_of: 'example of',
  related: 'related',
};

class Panel {
  private page: PageContext = { url: '', title: '', selection: '', excerpt: '' };
  private searchTimer?: number;
  private searchMode: 'semantic' | 'keyword' = 'semantic';

  async start(): Promise<void> {
    this.wireTabs();
    this.wireCapture();
    this.wireSearch();

    chrome.runtime.onMessage.addListener((msg) => {
      if (msg?.action === 'tabChanged') void this.refreshPage();
    });

    await this.refreshPage();
    await this.refreshFirstRun();
  }

  // --- chrome plumbing ------------------------------------------------

  private async readPage(): Promise<PageContext> {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const blank = { url: tab?.url ?? '', title: tab?.title ?? '', selection: '', excerpt: '' };
    if (!tab?.id || !/^https?:/.test(tab.url ?? '')) return blank;

    try {
      return (await chrome.tabs.sendMessage(tab.id, { action: 'getContext' })) ?? blank;
    } catch {
      // Content script not present (page loaded before install, or a restricted URL).
      return blank;
    }
  }

  private async refreshPage(): Promise<void> {
    this.page = await this.readPage();
    this.renderPassage();
    await this.refreshRelated();
  }

  // --- capture ---------------------------------------------------------

  private wireCapture(): void {
    const note = $<HTMLTextAreaElement>('note');
    const save = $<HTMLButtonElement>('save');

    note.addEventListener('input', () => {
      const filled = note.value.trim().length > 0;
      save.disabled = !filled;
      $('noteCount').textContent = String(note.value.trim().length);
      show($('captureHint'), !filled);
    });

    // Cmd/Ctrl+Enter saves, so capture never needs the mouse.
    note.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !save.disabled) void this.save();
    });

    save.addEventListener('click', () => void this.save());
    $('refreshSelection').addEventListener('click', () => void this.refreshPage());
  }

  private renderPassage(): void {
    const node = $('passage');
    const has = this.page.selection.length > 0;
    node.textContent = has
      ? this.page.selection
      : 'Select text in the page, or leave blank to note the article as a whole.';
    node.classList.toggle('is-empty', !has);
  }

  private async save(): Promise<void> {
    const note = $<HTMLTextAreaElement>('note');
    const save = $<HTMLButtonElement>('save');
    const hint = $('captureHint');

    save.disabled = true;
    save.textContent = 'Saving…';
    try {
      const saved = await api.createNote({
        url: this.page.url,
        title: this.page.title || this.page.url,
        passage: this.page.selection,
        note: note.value.trim(),
      });
      this.renderSavedNote(saved);
      note.value = '';
      $('noteCount').textContent = '0';
      hint.textContent = 'Saved.';
      show(hint, true);
      show($('welcome'), false);
      this.setOffline(false);
    } catch (err) {
      const offline = err instanceof ApiError && err.message === 'offline';
      this.setOffline(offline);
      hint.textContent = offline
        ? 'Could not reach the backend — your note was not saved.'
        : `Could not save: ${(err as Error).message}`;
      show(hint, true);
    } finally {
      save.textContent = 'Save note';
      save.disabled = note.value.trim().length === 0;
    }
  }

  private renderSavedNote(saved: Note): void {
    $('savedTitle').textContent = saved.title;

    const passage = $('savedPassage');
    passage.textContent = saved.passage;
    show(passage, Boolean(saved.passage));

    $('savedNote').textContent = saved.note;
    $('savedClaim').textContent = saved.claim || '—';
    $('savedQuestion').textContent = saved.open_question || '—';

    const tags = $('savedTags');
    clear(tags);
    saved.tags.forEach((tag) => tags.append(el('li', {}, tag)));

    const links = $('savedLinksList');
    clear(links);
    saved.links.forEach((link) => links.append(this.linkRow(link)));
    show($('savedLinks'), saved.links.length > 0);

    show($('saved'), true);
  }

  // --- related ---------------------------------------------------------

  private async refreshRelated(): Promise<void> {
    const strip = $('relatedStrip');
    const probe = this.page.selection || this.page.excerpt;
    if (!probe) return show(strip, false);

    try {
      const { hits } = await api.related({
        url: this.page.url,
        title: this.page.title,
        text: probe,
      });
      const list = $('relatedList');
      clear(list);
      hits.forEach((hit) => list.append(this.linkRow(hit)));
      show(strip, hits.length > 0);
      this.setOffline(false);
    } catch (err) {
      show(strip, false);
      if (err instanceof ApiError && err.message === 'offline') this.setOffline(true);
    }
  }

  private linkRow(link: Link): HTMLElement {
    return el(
      'li',
      {},
      el('span', { class: 'relation', 'data-relation': link.relation },
        RELATION_LABEL[link.relation] ?? 'related'),
      safeLink(link.url, link.title, 'entry-title'),
      el('span', { class: 'entry-note' }, link.note),
      el('div', { class: 'entry-meta' }, link.why || `${Math.round(link.score * 100)}% similar`),
    );
  }

  // --- search & recent --------------------------------------------------

  private wireSearch(): void {
    const q = $<HTMLInputElement>('q');
    const run = () => void this.runSearch();
    q.addEventListener('input', () => {
      window.clearTimeout(this.searchTimer);
      this.searchTimer = window.setTimeout(run, 250);
    });
    document
      .querySelectorAll<HTMLInputElement>('input[name="scope"]')
      .forEach((radio) => radio.addEventListener('change', run));
  }

  private async runSearch(): Promise<void> {
    const query = $<HTMLInputElement>('q').value.trim();
    const results = $('results');
    const empty = $('searchEmpty');
    clear(results);

    if (!query) return show(empty, false);

    const scope =
      document.querySelector<HTMLInputElement>('input[name="scope"]:checked')?.value ?? 'both';
    try {
      const { hits, mode } = await api.search(query, scope);
      this.searchMode = mode;
      hits.forEach((hit) => results.append(this.noteRow(hit.note, hit)));
      empty.textContent = hits.length
        ? ''
        : mode === 'keyword'
          ? 'No note contains those words. Keyword search needs roughly the right wording — ' +
            'add an embedding provider to search by meaning instead.'
          : 'Nothing yet. Notes you save become findable here by the shape of the idea.';
      show(empty, hits.length === 0);
      this.setOffline(false);
    } catch (err) {
      const offline = err instanceof ApiError && err.message === 'offline';
      this.setOffline(offline);
      empty.textContent = offline ? 'Backend unreachable.' : (err as Error).message;
      show(empty, true);
    }
  }

  private async refreshRecent(): Promise<void> {
    const list = $('recentList');
    const empty = $('recentEmpty');
    clear(list);
    try {
      const notes = await api.listNotes();
      notes.forEach((note) => list.append(this.noteRow(note)));
      show(empty, notes.length === 0);
      this.setOffline(false);
    } catch (err) {
      show(empty, true);
      if (err instanceof ApiError && err.message === 'offline') this.setOffline(true);
    }
  }

  private noteRow(note: Note, hit?: SearchHit): HTMLElement {
    const meta = [relative(note.created_at)];
    if (hit) {
      // A keyword score is relative to the best hit, not a similarity — don't
      // dress it up as a percentage match.
      meta.push(
        this.searchMode === 'keyword'
          ? `keyword match in your ${hit.matched_on === 'note' ? 'take' : 'reading'}`
          : `${Math.round(hit.score * 100)}% · matched your ${hit.matched_on === 'note' ? 'take' : 'reading'}`,
      );
    }

    return el(
      'li',
      {},
      safeLink(note.url, note.title, 'entry-title'),
      el('span', { class: 'entry-note' }, note.note),
      el('div', { class: 'entry-meta' }, meta.filter(Boolean).join(' · ')),
    );
  }

  // --- chrome & shell ---------------------------------------------------

  private wireTabs(): void {
    document.querySelectorAll<HTMLButtonElement>('.tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((t) => t.classList.remove('is-active'));
        tab.classList.add('is-active');

        const target = tab.dataset.view!;
        ['capture', 'search', 'recent'].forEach((view) => show($(view), view === target));
        show($('welcome'), false);
        if (target === 'recent') void this.refreshRecent();
      });
    });
  }

  /** First run gets a designed screen rather than an empty form. */
  private async refreshFirstRun(): Promise<void> {
    try {
      const health = await api.health();
      this.searchMode = health.search;
      const first = health.notes === 0;
      show($('welcome'), first);
      show($('capture'), !first);
      this.setOffline(false);

      // Say plainly which tier is running, including a key that is present but rejected.
      const mode = $('modeNote');
      if (health.embeddings.state === 'error') {
        mode.textContent = `Embeddings unavailable — ${health.embeddings.detail}`;
        show(mode, true);
      } else if (health.search === 'keyword') {
        mode.textContent =
          'Keyword search. Set OPENAI_API_KEY or run Ollama to search by meaning.';
        show(mode, true);
      } else {
        show(mode, false);
      }
    } catch {
      this.setOffline(true);
    }
  }

  private setOffline(offline: boolean): void {
    show($('offline'), offline);
  }
}

void new Panel().start();
