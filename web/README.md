# ElectroMind AI — Website

Static site for [ElectroMind AI](../README.md), built with **plain HTML, CSS and JavaScript** — no build step, no dependencies.

```
web/
├── index.html      # single landing page (hero, features, how-it-works, quick start, FAQ)
├── css/style.css   # dark editorial theme (Fraunces + JetBrains Mono)
├── js/main.js      # mobile nav, scroll-reveal, copy buttons, FAQ accordion
└── assets/icon.png # app logo (copy of ../assets/icon.png)
```

## Preview locally

Just open `index.html` in a browser — it works from `file://`.

## Publish on GitHub Pages

1. Push this repository to GitHub.
2. In the repo: **Settings → Pages**.
3. Under **Build and deployment**, set **Source = Deploy from a branch**.
4. Choose your branch (e.g. `main`) and the folder **`/web`** (or `/docs` if you renamed it), then **Save**.
5. Wait ~1 minute; the site goes live at `https://<username>.github.io/<repo>/`.

### Alternative — GitHub Actions

Create `.github/workflows/pages.yml`:

```yaml
name: Deploy web to GitHub Pages
on:
  push:
    branches: [main]
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: web
      - uses: actions/deploy-pages@v4
        id: deployment
```

Then in **Settings → Pages** set Source = **GitHub Actions**.

## Notes

- Update the GitHub link in `index.html` (`.nav__cta`) to point at your real repository URL.
- Fonts are loaded from Google Fonts; if you want zero external requests, self-host the font files and edit the `<link>` tags in `index.html`.
