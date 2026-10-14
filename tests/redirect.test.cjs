// The GitHub Pages stub in redirect/ must forward every old link with its path, query and
// hash intact; index.html and 404.html are the same page so both are checked.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

const target = 'https://projects.cristian-nichifor.com/romania-reforms/';
const cases = [
  ['/romania-reforms/', '', '', target],
  ['/romania-reforms', '', '', target],
  ['/romania-reforms/a/b', '?x=1', '#h', target + 'a/b?x=1#h'],
  ['/romania-reforms/public-pay/', '?lang=ro&x=%2F', '#scenario=%7B%22x%22%3A1%7D',
    target + 'public-pay/?lang=ro&x=%2F#scenario=%7B%22x%22%3A1%7D'],
  ['/romania-reforms-old/x', '', '', target + 'romania-reforms-old/x'],
];

for (const name of ['index.html', '404.html']) {
  const html = readFileSync(join(__dirname, '../redirect', name), 'utf8');

  test(`${name}: redirect preserves path, query and hash`, () => {
    const scripts = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)];
    assert.equal(scripts.length, 1, 'expected one redirect script');
    for (const [pathname, search, hash, expected] of cases) {
      const destinations = [];
      const location = { pathname, search, hash, replace: (url) => destinations.push(url) };
      vm.runInNewContext(scripts[0][1], { location }, { timeout: 1000 });
      assert.deepEqual(destinations, [expected], pathname + search + hash);
    }
  });

  test(`${name}: canonical, noindex, noscript and visible fallback agree`, () => {
    assert.ok(html.includes('rel="canonical" href="' + target + '"'));
    assert.ok(html.includes('<meta name="robots" content="noindex" />'));
    const fallback = html.match(/<noscript>([\s\S]*?)<\/noscript>/i);
    assert.ok(fallback, 'no-JavaScript fallback is required');
    assert.ok(fallback[1].includes('0; url=' + target));
    assert.ok(html.includes('<a href="' + target + '"'));
  });
}
