# Nats Report

A personal Washington Nationals news page (scores, stat leaders, roster moves, Top-30 prospect moves, news, and X posts) for the Nationals and their affiliates.

- Live: https://dlilley66.github.io/natsreport/
- `build.py` pulls the MLB Stats API, the MLB Pipeline prospect list, and the MLB.com and Google News RSS feeds, then writes a static `index.html`. It uses only the Python standard library.
- `x_posts.json` holds saved X posts. build.py can't reach X, so this file is updated by hand.
- A GitHub Actions workflow rebuilds and deploys the page daily at 11:15 UTC (6:15 AM CT) and can also be started manually.
- On iPhone, open the page in Safari and use Share > Add to Home Screen.
