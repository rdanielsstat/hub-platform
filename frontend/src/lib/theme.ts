/**
 * Theme persistence + the theme-color meta tag.
 *
 * The initial theme itself is resolved even earlier than this, by
 * public/theme-init.js, which index.html loads before React mounts (to
 * avoid a flash of the wrong theme). That script reads/writes the same
 * localStorage key as THEME_STORAGE_KEY below in a plain, duplicated form,
 * since it can't import this module. Keep the key literal in
 * public/theme-init.js in sync with this constant if it ever changes.
 */

export type Theme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'hub.theme'

export function setStoredTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // e.g. private browsing storage restrictions; the choice just won't persist
  }
}

/**
 * Syncs <meta name="theme-color"> to whatever --background currently
 * resolves to, so mobile browser chrome matches the active theme. Reads
 * the real computed style rather than duplicating the palette's hex
 * values here, so it can't drift from index.css. (The palette is
 * authored in oklch(); that's valid CSS Color 4 and theme-color accepts
 * any valid CSS <color>, so it's passed through as-is.)
 */
export function updateThemeColorMeta(): void {
  const meta = document.querySelector('meta[name="theme-color"]')
  if (!meta) return
  const color = getComputedStyle(document.body).backgroundColor
  if (color) meta.setAttribute('content', color)
}
