# Fruktovy Dvorets

> **Languages:** [English](README.md) · [Русский](README.ru.md)

Static storefront for a fruit shop at Sytninskaya Street 12 in Saint Petersburg:
25 catalog items, search, aisle and grid views, reorder basket, crate builder,
seasonal calendar, gallery, five themes and seller chat. The full Russian
documentation is in [README.ru.md](README.ru.md).

**Site:** https://ssrjkk.github.io/fruktovy/

No payment is taken on the page. Checkout creates an order; the shop replies in
Telegram with an SBP or card invoice, or the customer pays on pickup. Acquiring is
not connected.

## Run locally

```bash
python -m http.server 8080
```

Open http://127.0.0.1:8080/. `file://` opens the page, but ZIP export and repeated
asset requests require an HTTP server.

## Checks

```bash
node scripts/gate.mjs
python make_zip.py
```

The gate verifies catalog counts, generated image paths, palette contrast, visible
FAQ against JSON-LD, CSP, image dimensions and third-party hosts.

## Structure

- `index.html` — storefront markup, CSS, JavaScript and product data.
- `assets/` — local photos, fonts, icons, manifest and social preview.
- `scripts/gate.mjs` — static quality gate.
- `make_zip.py` — release archive builder.
- `AGENT_DEPLOY.md` — deployment and live-browser checklist.

## Design and data

The five palettes share one markup and data model. 2D mode is used on touch screens
and when `prefers-reduced-motion: reduce` is set. Product prices are edited in the
`PRODUCTS` array; the site has no server-side price API.

Fonts and photos are committed to the repository. The interactive map loads only
after the visitor explicitly opens it.

## Deployment

Push to `main`. GitHub Actions runs the quality gate and publishes to GitHub Pages.
The canonical URL is `https://ssrjkk.github.io/fruktovy/`.

## Documentation

- [Russian README](README.ru.md)
- [Deployment](AGENT_DEPLOY.md)
- [Asset credits](assets/CREDITS.txt)

## License

The repository license is not declared. Photos use the Pexels License and fonts use
the SIL Open Font License 1.1; details are in [assets/CREDITS.txt](assets/CREDITS.txt).
