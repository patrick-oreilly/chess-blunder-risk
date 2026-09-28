# Data

## Source

Approximately **4,300 of my own online chess matches**, retrieved from my personal Chess.com account
using the free **Published-Data API**. No scraping, no third-party dataset, no other players' games.

## Scope

Only **rated blitz** games of standard chess are used. Blitz is the only time control included, so
the whole dataset is measured under one clock regime. What is excluded, and why:

- **Bullet and rapid** — bullet runs at roughly 1-3 seconds per move and rapid at 15+ minutes, so
  mixing time controls would partly teach a model which control it is looking at rather than
  anything about blunders. Blitz (3-14 minutes) is a far tighter regime.
- **Games against the computer** — the rating-difference feature is meaningless against an engine.
- **Daily and correspondence games** — they have no per-move clock, so they cannot answer the
  secondary question about thinking time at all.
- **Variants such as Chess960** — the starting position changes the board state and the legal-move
  counts the features rely on.
- **Unfinished and aborted games** — no complete move sequence to label.

Restricting the data to blitz reduces the number of usable games below the ~4,300 total on the
account. The counts quoted in the proposal are therefore an upper bound until the acquisition
notebook reports the real figures.

## Licence

| Item                     | Terms                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Chess.com game records   | Chess.com Developer Terms — free use for educational purposes. **These terms do not grant redistribution rights.** |
| Stockfish 19             | GPLv3                                                                                                              |
| Engine evaluation labels | Generated locally by me; derived from the above                                                                    |

**Consequence:** the raw data and any derived per-position tables are **not committed to this
repository**. The `.gitignore` excludes `data/*.pgn`, `data/*.json`, `data/*.csv` and `data/*.parquet`
for that reason. What is committed is this file: enough for anyone to obtain the data themselves and
reproduce the work.

## Engine

Labels are generated with **Stockfish 19** (GPLv3), the binary installed locally at
`/opt/homebrew/bin/stockfish`. Centipawn values differ between engine releases, so the version, the
licence, the binary path and the evaluation settings have to be reported together — stating any one
of them alone does not make the labels reproducible.

The evaluation settings are fixed before labelling begins and recorded here:

- **Search limit:** 100,000 nodes. A fixed node count gives a predictable runtime across 250,000
  positions; a fixed depth does not, because depth 12 is quick in a quiet position and slow in a
  sharp one. This trades a conventional, easily explained setting for a predictable batch runtime.
- **`Threads`:** 1. Multi-threaded search is not deterministic, so a re-run could otherwise produce
  different labels for the same position.
- **`Hash`:** 16 MB. A fixed size keeps repeated runs comparable.

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
2. **Label** each position with Stockfish 19, recording centipawn loss per played move. The blunder
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
