// The parts every page of the site shares: the navigation between the simulators and the
// Content Security Policy. One module, so the landing page and seven separately built apps
// cannot drift apart. The apps apply it through `siteShell()` in their Vite config; the
// static pages in site/ carry its output, which tests/test_site_shell.py keeps identical.

export const SIMULATORS = Object.freeze([
  ['administrative-reform', 'Reforma administrativă', 'Administrative reform'],
  ['public-pay', 'Salarizarea publică', 'Public pay'],
  ['transport', 'Transport public', 'Public transport'],
  ['justitie', 'Reforma justiției', 'Justice reform'],
  ['impozit-teren', 'Impozitul pe teren', 'Land tax'],
  ['deconcentrare', 'Serviciile deconcentrate', 'Deconcentrated services'],
  ['companii-stat', 'Companiile statului', 'State companies'],
]);

// English labels: needs human review.
const NAV_TEXT = {
  ro: { label: 'Simulatoare', home: 'Toate simulatoarele' },
  en: { label: 'Simulators', home: 'All simulators' },
};

// Everything the pages load is their own: scripts, styles, data, map workers. Styles allow
// inline because the landing page and the apps set some at run time; nothing else does.
// frame-ancestors cannot be set from a meta tag and stays with the host.
export const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ');

export const CSP_META = `<meta http-equiv="Content-Security-Policy" content="${CSP}" />`;

export const NAV_STYLE =
  '<style>.rr-nav{margin:1.5rem 0 0;padding-top:.75rem;border-top:1px solid;' +
  'border-color:color-mix(in srgb,currentColor 20%,transparent);font-size:.8rem;line-height:1.6}' +
  '.rr-nav ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:.2rem .9rem}' +
  '.rr-nav a{color:inherit}.rr-nav a[aria-current="page"]{font-weight:600;text-decoration:none}</style>';

const NAV_MARKER = '<!-- rr-nav -->';

/**
 * The navigation for one page. `current` is the simulator's path ('' for the landing page),
 * `prefix` the way from the page to the site root ('../' inside a simulator).
 */
export function navHtml(current, prefix, lang = 'ro') {
  const text = NAV_TEXT[lang];
  const link = (path, label) => {
    const here = path === current ? ' aria-current="page"' : '';
    const href = path ? `${prefix}${path}/` : prefix || './';
    return `<li><a href="${href}"${here}>${label}</a></li>`;
  };
  const items = [
    link('', text.home),
    ...SIMULATORS.map(([path, ro, en]) => link(path, lang === 'en' ? en : ro)),
  ];
  return `<nav class="rr-nav" aria-label="${text.label}"><ul>${items.join('')}</ul></nav>`;
}

/** The page with the navigation at its marker (or at the end of the body) and the shared head. */
export function applyShell(html, { current, prefix = '../', csp = true }) {
  const nav = navHtml(current, prefix);
  let out = html.includes(NAV_MARKER) ? html.replace(NAV_MARKER, nav) : html.replace('</body>', `${nav}\n</body>`);
  const head = `${csp ? `${CSP_META}\n` : ''}${NAV_STYLE}\n`;
  out = out.replace('</head>', `${head}</head>`);
  return out;
}

/**
 * Vite plugin for a simulator. The policy is added to the built page only: the dev server
 * injects inline scripts of its own (React refresh, the HMR client) that it would block.
 */
export function siteShell(current) {
  return {
    name: 'romania-reforms-site-shell',
    transformIndexHtml(html, ctx) {
      return applyShell(html, { current, csp: !ctx.server });
    },
  };
}
