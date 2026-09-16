/** Typed client for the Memo backend. */

export interface Link {
  note_id: string;
  title: string;
  url: string;
  note: string;
  relation: 'agrees' | 'contradicts' | 'extends' | 'example_of' | 'related';
  score: number;
  why: string;
}

export interface Note {
  id: string;
  url: string;
  title: string;
  passage: string;
  note: string;
  claim: string;
  open_question: string;
  tags: string[];
  created_at: string;
  links: Link[];
}

export interface SearchHit {
  note: Note;
  score: number;
  matched_on: 'note' | 'passage';
}

export const DEFAULT_BACKEND = 'http://localhost:8000';

let backend = DEFAULT_BACKEND;

/** Read the saved backend URL. Falls back to the default if storage is empty. */
export async function loadBackend(): Promise<string> {
  try {
    const { backendUrl } = await chrome.storage.local.get('backendUrl');
    if (typeof backendUrl === 'string' && backendUrl) backend = backendUrl;
  } catch {
    // storage unavailable; keep the default
  }
  return backend;
}

export async function saveBackend(url: string): Promise<void> {
  backend = url.replace(/\/+$/, '');
  await chrome.storage.local.set({ backendUrl: backend });
}

export function currentBackend(): string {
  return backend;
}

export class ApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${backend}/v1${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError('offline');
  }
  if (res.status === 204) return undefined as T;
  if (!res.ok) {
    // FastAPI validation errors arrive as {detail: [{msg, ...}]}
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d: { msg?: string }) => d.msg ?? '').join('; ')
      : typeof detail === 'string'
        ? detail
        : `Request failed (${res.status})`;
    throw new ApiError(msg.replace(/^Value error, /, ''));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () =>
    request<{
      status: string;
      notes: number;
      search: 'semantic' | 'keyword';
      embeddings: { provider: string; model: string; state: string; detail: string };
      enrichment: string;
    }>('/health'),

  createNote: (body: { url: string; title: string; passage: string; note: string }) =>
    request<Note>('/notes', { method: 'POST', body: JSON.stringify(body) }),

  listNotes: (limit = 50) => request<Note[]>(`/notes?limit=${limit}`),

  deleteNote: (id: string) => request<void>(`/notes/${id}`, { method: 'DELETE' }),

  search: (q: string, scope: string) =>
    request<{ query: string; mode: 'semantic' | 'keyword'; hits: SearchHit[] }>(
      `/search?q=${encodeURIComponent(q)}&scope=${scope}`,
    ),

  related: (body: { url: string; title: string; text: string }) =>
    request<{ hits: Link[] }>('/related', { method: 'POST', body: JSON.stringify(body) }),
};
