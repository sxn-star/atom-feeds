# atom-feeds

A self-updating repository of Atom 1.0 feeds for academic publications and other sources that don't publish their own feed.

Feeds are regenerated **daily at 06:00 UTC** via GitHub Actions and committed back to this repo. Subscribe to the raw file URL in any feed reader (Feeder, NetNewsWire, Reeder, etc.).

---

## Available feeds

| Feed | Source | Raw URL |
|------|--------|---------|
| Bernardo Kastrup – Academic Papers | [bernardokastrup.com/p/papers](https://www.bernardokastrup.com/p/papers.html) | [kastrup-papers.atom](feeds/kastrup-papers.atom) |
| Levin Lab – Peer-Reviewed Papers | [drmichaellevin.org/publications](https://www.drmichaellevin.org/publications/) | [levin-lab-publications.atom](feeds/levin-lab-publications.atom) |

> **Subscribe URL pattern:**
> `https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/atom-feeds/main/feeds/FEED_SLUG.atom`

---

## Subscribing to feeds you find yourself

If you come across an RSS or Atom feed URL you want to track alongside the scraped feeds, add it to **`subscriptions.yml`** at the root of the repo — no code required.

### 1 — Edit `subscriptions.yml`

Open the file and add an entry under the `feeds:` list:

```yaml
feeds:
  - title: Quanta Magazine
    url: https://www.quantamagazine.org/feed/
    site_url: https://www.quantamagazine.org/
    category: Science

  - title: Gwern.net
    url: https://www.gwern.net/feed
    category: Research

  - title: Some Paywalled Blog
    url: https://example.com/feed.xml
    # category omitted → filed under "Uncategorized"
```

| Field | Required | Notes |
|-------|----------|-------|
| `url` | **yes** | The direct RSS or Atom feed URL |
| `title` | **yes** | Display name in your feed reader |
| `site_url` | no | Homepage of the site (written as `htmlUrl` in OPML) |
| `category` | no | Folder name in OPML; defaults to `Uncategorized` |
| `description` | no | Private note — not written to the OPML output |

You can edit the file directly on GitHub (click the pencil icon) or by cloning the repo locally. Commit the change to `main`.

### 2 — Regenerate the OPML

Go to **Actions → Generate OPML → Run workflow** and click **Run workflow**. The action will rebuild `feeds/subscriptions.opml` and commit it automatically.

### 3 — Import or subscribe

**Option A — Import once:** Download `feeds/subscriptions.opml` and import it into your feed reader (File → Import OPML, or similar). Repeat after adding more feeds.

**Option B — Subscribe to the OPML URL directly** (readers that support live OPML, e.g. Inoreader, FreshRSS):

```
https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/atom-feeds/main/feeds/subscriptions.opml
```

The OPML contains both the scraped feeds from this repo and every URL you've added to `subscriptions.yml`.

---

## Setup (first time)

### 1 — Create the GitHub repository

```bash
# Install the GitHub CLI if you don't have it
# https://cli.github.com/

gh repo create atom-feeds --public --description "Self-updating Atom feeds for academic publications"
```

Or create it manually at [github.com/new](https://github.com/new).

### 2 — Push this code

```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/atom-feeds.git
# copy these files in, then:
git add .
git commit -m "init: atom-feeds framework"
git push
```

### 3 — Allow Actions to write to the repo

In your repository on GitHub:  
**Settings → Actions → General → Workflow permissions → Read and write permissions** ✓ → Save

### 4 — Replace the placeholder in feeds

Open `scrapers/base.py` and replace `YOUR_GITHUB_USERNAME` with your actual GitHub username in the `<link rel="self">` line. Then push.

### 5 — Trigger a first run

**Actions tab → Update Atom Feeds → Run workflow** — this re-scrapes everything and commits fresh `.atom` files.

---

## How to add a new feed

### Option A — Simple (requests-based, for sites that don't block bots)

```python
# scrapers/my_new_source.py
from .base import BaseScraper, Paper
import requests
from bs4 import BeautifulSoup

class MyNewSourceScraper(BaseScraper):
    FEED_SLUG     = "my-new-source"
    FEED_TITLE    = "My New Source – Papers"
    FEED_SUBTITLE = "Papers from My New Source."
    SOURCE_URL    = "https://example.com/papers/"
    AUTHOR_NAME   = "Author Name"
    AUTHOR_URI    = "https://example.com/"

    def scrape(self):
        r = requests.get(self.SOURCE_URL, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; atom-feeds-bot/1.0)"
        })
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "lxml")
        # ... parse and return list[Paper]
```

### Option B — Browser-based (for sites that block plain requests)

```python
from playwright.sync_api import sync_playwright

def _fetch_html(self) -> str:
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(self.SOURCE_URL, wait_until="networkidle", timeout=60_000)
        html = page.content()
        browser.close()
    return html
```

### Register the scraper

```python
# scrapers/__init__.py
from .levin_lab import LevinLabScraper
from .my_new_source import MyNewSourceScraper   # ← add import

ALL_SCRAPERS = [
    LevinLabScraper(),
    MyNewSourceScraper(),   # ← add instance
]
```

That's all — the next scheduled run will generate the new `.atom` file.

---

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium

# Regenerate all feeds
python generate_all.py

# Regenerate a specific feed (partial slug match)
python generate_all.py levin
```

---

## Feed reader setup (Feeder for Android)

1. Open Feeder → **+** → **Add feed by URL**
2. Paste the raw GitHub URL:
   ```
   https://raw.githubusercontent.com/YOUR_GITHUB_USERNAME/atom-feeds/main/feeds/levin-lab-publications.atom
   ```
3. Done — Feeder will poll this URL on its normal schedule, always getting the latest version.
