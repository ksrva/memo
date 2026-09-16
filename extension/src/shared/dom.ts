/**
 * Tiny DOM helpers.
 *
 * Everything user- or model-supplied goes in through `textContent`. v1 built
 * these lists with innerHTML and template literals, which handed any page that
 * could get text into a note a script-execution primitive in the panel.
 */

type Attrs = Record<string, string | undefined>;

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined) continue;
    if (key === 'class') node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) {
    node.append(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

export const $ = <T extends HTMLElement>(id: string): T => {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node as T;
};

export function clear(node: HTMLElement): void {
  node.replaceChildren();
}

export function show(node: HTMLElement, visible: boolean): void {
  node.hidden = !visible;
}

/** A link that opens in a new tab, with the href validated as http(s). */
export function safeLink(href: string, text: string, cls?: string): HTMLElement {
  let ok = false;
  try {
    ok = ['http:', 'https:'].includes(new URL(href).protocol);
  } catch {
    ok = false;
  }
  return ok
    ? el('a', { href, target: '_blank', rel: 'noreferrer noopener', class: cls }, text)
    : el('span', { class: cls }, text);
}

export function relative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 30 ? `${days}d ago` : new Date(then).toLocaleDateString();
}
