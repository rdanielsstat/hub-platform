// Resolve and apply the theme before first paint, so there's no flash of
// the wrong theme. Loaded by index.html as a plain, blocking <script src>,
// not inline: the Content-Security-Policy (infra/hub/frontend.tf) allows
// scripts from 'self' only, with no inline exceptions. Keep 'hub.theme' in
// sync with THEME_STORAGE_KEY in src/lib/theme.ts; this can't import that
// module, since it has to run synchronously, standalone, this early.
;(function () {
  try {
    var stored = localStorage.getItem('hub.theme')
    var dark =
      stored === 'dark' ||
      (stored !== 'light' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches)
    if (dark) {
      document.documentElement.classList.add('dark')
      var meta = document.querySelector('meta[name="theme-color"]')
      // Approximate; src/lib/theme.ts's updateThemeColorMeta()
      // corrects this to the exact computed color once React mounts.
      if (meta) meta.setAttribute('content', '#18181d')
    }
  } catch (e) {
    // localStorage/matchMedia unavailable; fall back to light.
  }
})()
