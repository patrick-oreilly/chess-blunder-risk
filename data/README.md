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

| Item                     | Terms                                                                       |
| ------------------------ | --------------------------------------------------------------------------- |
| Chess.com game records   | My own public games, retrieved through Chess.com's Published-Data API       |
| Stockfish 19             | GPLv3                                                                       |
| Engine evaluation labels | Generated locally by me; derived from the above                             |

**Not in git:** the raw archives and the derived tables are generated, large, and reproducible from
the public API, so the `.gitignore` keeps `data/raw/` and `data/processed/` out of the repository.
What is committed is this file: enough for anyone to obtain the data themselves and reproduce the
work. The processed tables are included in the Canvas submissions so the notebooks can be run
without repeating the two-hour labelling job.

## Engine

Labels are generated with **Stockfish 19** (GPLv3). The binary is found through the `STOCKFISH_PATH`
environment variable if it is set, otherwise as `stockfish` on `PATH`; it was installed with
Homebrew (`/opt/homebrew/bin/stockfish`) and pinned so it cannot upgrade mid-project. Centipawn
values differ between engine releases, so the version and the evaluation settings have to be
reported together — stating either alone does not make the labels reproducible.

The evaluation settings are fixed before labelling begins and recorded here:

- **Search limit:** 100,000 nodes. A fixed node count gives a predictable runtime across 260,030
  positions; a fixed depth does not, because depth 12 is quick in a quiet position and slow in a
  sharp one. This trades a conventional, easily explained setting for a predictable batch runtime.
- **`Threads`:** 1. Multi-threaded search is not deterministic, so a re-run could otherwise produce
  different labels for the same position. Labelling is parallelised across positions instead, with
  one single-threaded engine per worker process.
- **`Hash`:** 16 MB, **cleared before every position** (a `ucinewgame` per search). Without the
  clear, a search inherits whatever the same engine process searched before it, so a score depends
  on the worker count and game order: an earlier version of the labeller flipped 3 of 360 labels
  when the game order was reversed. With it, the same 4 games labelled with four workers in index
  order and with one worker in reverse order give identical tables.
- **Move history:** each position is sent to the engine with the game's moves, not as a bare FEN,
  so repetition draws are visible to the search.

### The blunder label

Blunders are judged with **Lichess's move-judgement rules**, so the definition is an established one
rather than one invented for this project. Source: the Lichess server,
[`lila`](https://github.com/lichess-org/lila) — `ui/lib/src/ceval/winningChances.ts` for the
conversion and `modules/tree/src/main/Advice.scala` for the judgements.

**Ordinary score before and after the move.** Each score is clamped to ±1000 centipawns and turned
into winning chances, shown here as a 0–100 win percentage:

```
win% = 50 + 50 × (2 / (1 + exp(−0.00368208 × cp)) − 1)
```

A drop of **15 percentage points** for the player who moved is a blunder (Lichess's 0.3 on its
−1..1 scale).

**A forced mate before or after the move.** The curve is not used. Lichess's two mate rules apply:

- **Mate created** — moving into a forced mate against you is a blunder, unless you were already at
  −700cp or worse.
- **Mate lost** — giving up your own forced mate is a blunder, unless you are still at +700cp or
  better afterwards.

Every other mate transition (a mate getting longer, or a lost position staying lost) carries no
judgement. The rule that applied is stored per move in `mate_sequence`.

**Why not a centipawn threshold.** The Milestone 1 proposal used a drop of 200 centipawns. That
treats every 200cp the same, but it is not: +150 to −150 turns a likely win into a likely loss,
while +2000 to +1360 changes nothing about the result. On a 4-game sample the centipawn definition
labelled 32 blunders, 13 of them moves made from positions already decided by more than ten pawns
and two of them moves *into* a forced mate — the best move on the board.

Other choices inside the definition, all of which move the reported figures:

- **One evaluation per position**, reused for the move that follows it. A game of _k_ plies therefore
  costs _k + 1_ evaluations rather than _2k_.
- **Finished games are scored directly.** Checkmate is a mate; every draw — stalemate, insufficient
  material, and the threefold repetition and 50-move rule, which Chess.com applies automatically —
  is level (50%).
- **Win percentages are stored for every move**, using Lichess's mate mapping for mates (mate in
  _n_ counts as (21 − min(10, _n_)) × 100 centipawns), but for mate moves the label comes from the
  mate rules, not from the stored drop.
- **Centipawn values are stored for reporting**, clamped to ±1000 with any mate at the clamp, and
  `cp_loss` capped at 1000. The label does not use them.
- **The threshold is a choice, not a fact.** The blunder rate at 10, 15 and 20 points is reported on
  the full dataset to show how far the definition moves it.

### Game stage

Game stage is a heuristic, read off the position before the move:

- **Opening:** the first 20 plies.
- **Endgame:** total material on the board (both sides, pawn 1, knight/bishop 3, rook 5, queen 9) is
  20 points or fewer.
- **Middlegame:** everything else.

Both cut-offs are choices, set in `src/chess_blunder/features.py`.

### Ratings

Chess.com archives record each player's rating **after** the game, so it encodes the game's result:
the author's rating change matches that game's result in 98.3% of games. The table therefore carries
`my_rating_pre` — the rating after the author's previous game, which is the rating going into this
one — and no opponent rating, because the opponent's pre-game rating cannot be recovered. The first
game in the dataset has no previous rating.

## How to obtain it

The API is public and requires no authentication for public game archives:

- Player archives (monthly game URLs):
  `https://api.chess.com/pub/player/{username}/games/archives`
- Games for a month:
  `https://api.chess.com/pub/player/{username}/games/{YYYY}/{MM}`

The exact username and date range used are recorded in the acquisition notebook
(`notebooks/01_...`), so the retrieval is reproducible rather than described in prose.

## Preparation

The whole pipeline is two steps, run from the repository root (setup is in the main
[`README.md`](../README.md)):

1. **Download and index** — run `notebooks/01_data_acquisition.ipynb`. It caches the monthly archives
   in `data/raw/` as JSON, up to `END_MONTH` in `src/chess_blunder/config.py` (`2026-09`), and writes
   `data/processed/games_index.csv`. Months already on disk are not re-fetched, so the September 2026
   archive is the one fetched on 30 September 2026.
2. **Label and build** — `PYTHONPATH=src python -m chess_blunder.build_dataset --workers 8` labels
   every position with Stockfish and writes `data/processed/positions.parquet`, one row per ply. It
   checkpoints after every game, so an interrupted run is resumed by running it again. Games that
   fail are recorded and listed at the end rather than stopping the run.

Two data-quality issues are known before any modelling and are handled by design:

- **Leakage.** Moves within a game share tactical context, and the author's play changes over four
  years. The test set is therefore the most recent 20% of games by date, and tuning uses
  cross-validation grouped by `game_id`, never a random split of rows. Columns that are derived from
  the label (`cp_after`, `cp_loss`, `win_after`, `win_loss`, `mate_sequence`, `mate_involved`) and
  the after-the-move clock (`seconds_remaining`, `seconds_spent`) are never inputs to the predictive
  model.
- **Class imbalance.** Blunders are a minority of moves (the rate is measured on the full dataset
  in the data audit), so accuracy is not a usable metric. Precision–recall AUC is the primary
  metric, with ROC-AUC alongside it.

## Privacy

The data contains only my own public game records. Opponents appear only as their public Chess.com
usernames, which are kept in the local index for traceability and never used as features or
published. Nothing is committed, so there is no GDPR or confidentiality exposure.
