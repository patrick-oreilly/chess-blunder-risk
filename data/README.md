# Data

## Source

My own online chess matches, retrieved from my personal Chess.com account using the free
**Published-Data API**. No scraping, no third-party dataset, no other players' games.

The account holds **4,373 games across 46 monthly archives**, spanning `2022/10` to `2026/09`.
Filtering to the scope below leaves **4,010 rapid games**, and dropping two games that were
abandoned before the first move leaves **4,008** — the working dataset. Those games contain
**260,030 plies**, so roughly 260,000 board positions to label.

## Scope

Only **rated rapid** games of standard chess are used. Everything else is excluded. These counts are
real totals from the account, not estimates:

- **Bullet (11 games) and blitz (41)** — too few to support a separate conclusion, and mixing time
  controls would partly teach a model which control it is looking at rather than anything about
  blunders.
- **Daily and correspondence (308)** — a different regime, measured in hours and days rather than
  seconds. Their `%clk` field also records elapsed think time rather than a countdown, so the
  "seconds remaining" feature does not exist for them. See _Clock data_ below.
- **Unrated games (5)** — across all the classes above; casually arranged or against the computer, so
  rating difference is meaningless.
- **Variants such as Chess960 (2)** — the starting position changes the board state and the
  legal-move counts the features rely on.
- **Abandoned before the first move (2)** — headers only, no moves to label. Identified by a PGN
  that parses to zero plies.

The working dataset is concentrated by time control as well: **3,872 of the 4,008 games are
10-minute (600s)**, with the remainder at 900+10 (94), 1800 (40) and 3600 (2). A near-single time
control is a strength here — the clock features are comparable across the dataset rather than being
confounded with the time control.

### Clock data

All **4,008** in-scope games carry a `%clk` comment on every ply — the number of clock comments
equals the ply count in every single game, with no exceptions. Time spent on a move is therefore
computable everywhere, so the secondary question is answerable across the whole dataset rather than
a subset of it.

The only rapid games without clock data were also the only two with no moves: both were abandoned
before the first move, and are excluded for having nothing to label.

Daily games also carry `%clk`, but it is not a countdown: values rise and fall (`0:00:40`,
`0:22:50`, `0:01:16`) because the field records elapsed thinking time instead. That is a second
reason for excluding them, beyond the difference in regime.

### Game length

Plies per game run from **1 to 206**, with a median of 61. The distribution has a real short tail:
51 games are under 10 plies and 198 are under 20, almost all early resignations rather than broken
records. Those games carry very little positional context, so `games_index.csv` keeps a ply count
per game and the analysis can test whether they matter instead of dropping them on a guess.

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
