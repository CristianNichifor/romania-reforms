# Native Civic UI Adoption

The statistics entry imports the CSS-only Civic UI v0.4.0 artifact, not React or
the React package. Map controls stay local. The two Vite entries remain separate,
so reading statistics does not download MapLibre and opening the map does not
import Civic UI CSS.

`scripts/vendor-civic-css.mjs --update` downloads the pinned public release,
verifies its SHA-256 and vendors only selected CSS, MIT license and native-contract
documentation. Normal builds verify those local bytes with no network request.
`src/vendor/civic-ui/provenance.json` records the release and per-file checksums.
No npm account, remote font or external runtime service is required.

Release: `https://github.com/CristianNichifor/civic-ui/releases/download/v0.4.0/civic-ui-css-0.4.0.tgz`

SHA-256: `269dc6d01f4da09707521229111ac55011f78f55518a7c8d73d660503ed84de7`

## Adopted

- `#scope` and `#tier`: labeled native selects inside `.civic-field`, using the
  browser arrow and a 44px minimum control height.
- `#load-proposal`: native `.civic-button`, retaining loading, retry and hidden
  states owned by the existing statistics code.
- Warning and national-scope paragraphs: `.civic-notice` with the existing
  justice warning/surface tokens. A local block-flow adapter preserves prose
  containing inline emphasis or code instead of treating it as an icon/body row.
- Filter status uses a polite native status announcement.

`src/civic.css` maps Civic UI roles to the existing justice light/dark tokens.
Control borders use the existing faint-ink token for a discernible boundary;
there is no party palette, global reset or library-owned theme switch.

Charts, routes, filtering, proposed-court calculations, map modes, native ranges,
reader dialog and datasets remain host-owned. This change does not add a service
worker or promise cold offline reloads for uncached data.

See [BROWSER_BASELINES.md](BROWSER_BASELINES.md) for browser and parity checks.
