# NetConfig UI/CSS Regression Review — 2026-09-22

**Baseline reviewed:** Release 50 / MC-2.1 Sensor History Database Foundation (`2.0.0-50`)  
**Status:** `IMPLEMENTED_TESTING_DEFERRED`  
**Scope:** restart the WebUI/CSS review from the current source baseline after the NetFlow conditional-visibility defect. This review does not claim MC-2.2+ implementation and does not build an RPM.

## Findings corrected

1. **Dashboard hidden/display conflict** — `devnoresults` used persistent `style="display:none"` while JavaScript toggled only the HTML `hidden` property. This was the same class of defect that hid the NetFlow section. The dashboard now uses only `hidden`, with `[hidden]{display:none!important}` as the canonical visibility mechanism.
2. **Stale CSS custom properties** — legacy references to `--txt`, `--bad`, `--brass`, `--brass2`, and `--muted` survived the green-theme consolidation even though those tokens were no longer defined. References were migrated to current tokens (`--text`, `--red`, `--warn`, `--navy`, `--grey`).
3. **Checkbox/radio sizing** — the global `input{width:100%}` rule also applied to native checkbox/radio controls. Some pages relied on inline `width:auto`, while protocol settings had no override. A global type-specific rule now keeps checkbox/radio controls at native width.
4. **Graph theme bypass** — live-interface graph cards still injected CSS through JavaScript (`style.cssText`) and hard-coded light-theme colors. Runtime graph markup now uses the existing theme classes and token-backed path classes.
5. **Mobile top bar wrapping** — the mobile header gave `.top-right` 100% width but did not allow the parent header to wrap. The <=760px rule now enables wrapping and lets the brand text break safely.
6. **Mobile wide-table overflow** — the Protocols table exceeded the viewport at 390px. Narrow-screen tables now scroll inside their own box instead of widening the document.
7. **Help long-code overflow** — Help forced inline code to `white-space:nowrap`, producing document-level horizontal overflow on long commands/filenames. Narrow-screen Help code can now wrap safely.
8. **Dark-theme neutral/error colors** — `.b-dim`, `.err`, and `.vault-lock` retained light-only hard-coded colors. They now use theme-aware tokens.
9. **Release truth drift found during regression** — the spec already declared Release 50 while canonical Markdown still pointed at Release 49 and `test_repo_hygiene.py` still required Release 48. Canonical active-baseline markers and the repository truth gate were synchronized to Release 50 / MC-2.1. Historical Release 48 evidence sections remain historical rather than being rewritten as current results.

## CSP/style behavior reviewed

NetConfig enforces `style-src-attr 'none'`. Server-rendered `style="..."` attributes are intentionally converted by `apply_csp_nonce()` into deterministic generated classes placed in a nonce-authorized `<style>` block. Representative rendered pages were checked after this transformation and contained **zero residual inline `style` attributes**.

The review found no remaining undefined CSS custom properties in `web.py`, `web_ui.py`, or `web_ops.py`, and no remaining runtime `style="display:none"` visibility pattern in the console source.

## Browser rendering smoke

Representative server-rendered HTML was passed through the real CSP style transformation and evaluated in headless Chromium at **1440x1000** and **390x844**.

Pages checked:

- Dashboard
- Protocols / Device Collection
- Settings
- Help
- Network Device Edit
- Application Device Edit

Observed after fixes:

- no document-level horizontal overflow on the checked pages at either width;
- no duplicate element IDs on the checked pages;
- no `[hidden]` element computed as visible;
- dashboard `No devices match your search` changes from hidden to visible for a no-match search;
- Network-device NetFlow section computes to `display:block`;
- non-network NetFlow section computes to `display:none`;
- protocol checkbox widths compute to native 13px rather than full-row width;
- dark-theme sample: body background `rgb(15, 23, 18)`, dim badge background `rgb(21, 32, 26)`, dim text `rgb(174, 189, 179)`, and error border `rgb(255, 140, 125)`.

Direct Chromium navigation to the loopback test server is blocked by the execution environment, so browser layout checks used captured server-rendered HTML. The existing HTTP-level WebUI tests still exercise the real built-in server routes.

## Automated evidence

Focused CSS/WebUI/CSP regression:

```text
27 passed
0 failed
```

Full repository regression, executed in bounded groups:

```text
248 passed
8 skipped
0 failed
```

The eight skips remain explicit environment/live prerequisites:

- 1 Git metadata/index-mode check unavailable in the source archive;
- 3 live PostgreSQL core integration cases;
- 1 PostgreSQL backup/restore integration case;
- 3 protocol-service integration cases.

`python3 -m compileall -q opt/netconfig/netconfig` also passes.

## Remaining qualification boundary

This review does not promote the project to `TESTED` or `RELEASED`. Real browser testing against a deployed AlmaLinux service, production CSP reporting, full dark/light visual review across every route, live PostgreSQL/protocol/device gates, and other production qualification remain deferred. RPM build/test remains intentionally deferred until the roadmap is complete.
