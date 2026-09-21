# Data

## Source

Approximately **4,300 of my own online chess matches**, retrieved from my personal Chess.com account
using the free **Published-Data API**. No scraping, no third-party dataset, no other players' games.

## Licence

| Item                     | Terms                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Chess.com game records   | Chess.com Developer Terms — free use for educational purposes. **These terms do not grant redistribution rights.** |
| Stockfish 16             | GPLv3                                                                                                              |
| Engine evaluation labels | Generated locally by me; derived from the above                                                                    |

**Consequence:** the raw data and any derived per-position tables are **not committed to this
repository**. The `.gitignore` excludes `data/*.pgn`, `data/*.json`, `data/*.csv` and `data/*.parquet`
for that reason. What is committed is this file: enough for anyone to obtain the data themselves and
reproduce the work.

## How to obtain it

The API is public and requires no authentication for public game archives:

- Player archives (monthly game URLs):
  `https://api.chess.com/pub/player/{username}/games/archives`
- Games for a month:
  `https://api.chess.com/pub/player/{username}/games/{YYYY}/{MM}`

The exact username and date range used are recorded in the acquisition notebook
(`notebooks/01_...`), so the retrieval is reproducible rather than described in prose.

## Preparation

1. **Download** the monthly archives into `data/raw/` as JSON.
2. **Label** each position with Stockfish 16, recording centipawn loss per played move. The blunder
   target is a drop of **200 centipawns or more**.
3. **Build** the per-position feature table into `data/processed/`.

Two data-quality issues are known before any modelling and are handled by design:

- **Leakage.** Moves within a game share tactical context (the opening played, how familiar it is).
  Train and test are therefore split by whole game using `game_id`, never by random row.
- **Class imbalance.** Roughly 13.6% of moves are blunders, so accuracy is not a usable metric.
  ROC-AUC and precision–recall AUC are the primary metrics.

## Privacy

The data contains only my own public game records. There is no personal or third-party data, so there
is no GDPR or confidentiality exposure.
