# Lanka News Tracker

A mobile-responsive GitHub Pages news archive that preserves the first time **this collector** detected an RSS article. Headlines link to their original publishers. It also records the publisher's original claimed publication timestamp separately.

## Set up (GitHub)

1. Create a new **public** GitHub repository, e.g. `lanka-news-tracker`, and upload all files including `.github/workflows/collect.yml` and the initially empty `data/news.json`. Easiest: unzip the download and upload its contents using GitHub's Add file > Upload files (hidden `.github` directories may be easiest to add with Git on a computer).
2. In repository **Settings > Actions > General > Workflow permissions**, choose **Read and write permissions** and save. If this option is blocked by organization policy, request permission from the owner.
3. Open **Actions > Collect news > Run workflow**. Check its log; if publisher feeds fail, inspect the `Feed errors` status and adjust verified RSS sources in `collector.py`.
4. Under **Settings > Pages**, choose **Deploy from a branch**, select `main` and `/ (root)`, and save. Open `https://YOUR-USERNAME.github.io/lanka-news-tracker/` once deployed.
5. The Actions cron requests a run every 5 minutes; GitHub may delay or skip scheduled runs, and RSS feeds themselves may lag behind the publisher's website. This is *not* guaranteed instant breaking-news monitoring.

## What the prototype does and does not prove

- Default sources: Daily Mirror (breaking news), The Island, EconomyNext. Expand `SOURCES` with feeds tested by you, respecting feed and publisher conditions. Ada Derana, Newsfirst and Hiru are **not connected yet**.
- Groups headlines conservatively using overlapping words within 72 hours. Different Sinhala/English headlines about the same incident may appear in separate stories; unrelated incidents may occasionally be grouped. This is a heuristic, not verified event identification.
- Orders matched articles by first observed publisher publication timestamp, falling back to the collector's first-seen time if unavailable. An article may be backdated or its publication timestamp changed; neither feed polling nor the webpage proves the actual first publication time. The app preserves the original observed timestamp and first-seen time, and records any later changed date in `latest_claimed_published_at`.
- Historical data begins with the first successful collection. It cannot reconstruct earlier deleted RSS entries or social/broadcast first reports.
- GitHub public repository means the archive is visible to everyone. Do not store secrets in this repository.
- It stores only headline, timestamp, and original URL (not entire copyrighted articles).
- GitHub Pages is the user interface; GitHub Actions is the scheduled backend. Opening the HTML directly as `file://` is not supported.

## Local testing

```bash
pip install -r requirements.txt
python collector.py
python -m http.server 8000
```
Open http://localhost:8000/ . Network access is required for collection. No feed connectivity has been verified in this build environment; inspect actual run logs after deployment.
