# Lanka Puvath Live

A GitHub Pages + GitHub Actions Sri Lankan news tracker that keeps the visual style of the original Lanka Puvath HTML while adding:

- **Breaking / Latest** feed
- **Incident Timeline** view
- **First-report tracking** using publisher timestamps when available, otherwise the first time this collector saw the article
- Categories: Main, Politics, Sports, Business, World
- Source health indicators
- No Anthropic / OpenAI / paid news API required

## Deploy / update your existing repository

Upload/replace these files in the repository root:

- `index.html`
- `collector.py`
- `requirements.txt`
- `data/news.json` (only for a fresh install; keep your existing one if you want to preserve history)
- `.github/workflows/collect-news.yml`

Then go to **Actions → Collect news → Run workflow**.

In **Settings → Actions → General → Workflow permissions**, select **Read and write permissions**.

GitHub Pages should deploy from the `main` branch root.

## Important meaning of “FIRST”

The app can prove only the earliest report **among the sources it monitors and successfully retrieves**. RSS feeds may update late, publisher timestamps can be edited, homepage fallback does not always expose publication time, and GitHub scheduled workflows can be delayed. Therefore the UI separately stores:

- `published_at`: publisher-supplied time, if available
- `first_seen_at`: immutable time this collector first discovered the article

## Source reliability

Daily Mirror, EconomyNext and The Island are configured with RSS feeds. Ada Derana, Hiru News, News First, ITN and Lankadeepa use RSS auto-discovery when advertised by the site and conservative homepage discovery otherwise. Website layouts can change, so check the source-status chips at the top of the app.

## Improve incident matching later

The current matcher deliberately avoids aggressive merges. It groups similar headlines within 72 hours using Unicode word overlap. Sinhala and English reports of the same event may not cluster together because they use different languages. A later version can add multilingual embeddings or an AI service if you want stronger cross-language incident matching.
