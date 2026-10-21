# Chess Blunder Risk

Can a machine learning model predict whether a player will make a major tactical blunder on their
next move?

**CT4101 Machine Learning — Portfolio Project**
Patrick O'Reilly — 23366866

## The prediction task

Binary classification: **will the next move be a blunder?**

A blunder is judged with **Lichess's move-judgement rules** applied to Stockfish 19 evaluations: a
move that drops the mover's estimated win probability by **15 percentage points or more**, or, where
a forced mate is involved, a move that walks into one or throws one away. That threshold is a
choice, not a fact, changing it changes every reported figure, so it is stated up front rather than
buried. The Milestone 1 proposal used a 200-centipawn drop; why that changed is in
[`data/README.md`](data/README.md#the-blunder-label).

The secondary question whether thinking time still predicts blunders once position difficulty is
accounted for carries the most interpretation risk, because a naive reading of it suggests "play
faster", which is not advice this project supports.

## Data

4,373 games from my own Chess.com account via the free Published-Data API, filtered to 4,008 usable
rapid games, labelled locally with Stockfish 19. 260,030 plies, so roughly 260,000 board positions.

Source, licence and preparation steps are in [`data/README.md`](data/README.md). **The data is not
committed to this repository**: it is generated and reproducible from the public API. The processed
tables are included in the Canvas submissions.

## Setup

Requires **Python 3.13** and **Stockfish 19**.

```bash
# Stockfish 19 (macOS; on Linux use your package manager or the official binary)
brew install stockfish && brew pin stockfish
# If stockfish is not on PATH, point the project at it:
# export STOCKFISH_PATH=/path/to/stockfish

python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the work

From the repository root, with the virtual environment active:

1. **Download and index the games** — run `notebooks/01_data_acquisition.ipynb` top to bottom. It
   caches the Chess.com archives (up to September 2026) in `data/raw/` and writes
   `data/processed/games_index.csv`.
2. **Label every position** —

   ```bash
   PYTHONPATH=src python -m chess_blunder.build_dataset --workers 8
   ```

   About 2 hours on 8 cores. It checkpoints after every game, so if it is interrupted, run the same
   command again to resume. It writes `data/processed/positions.parquet`, one row per ply.

## Repository layout

| Path            | Purpose                                                                      |
| --------------- | ---------------------------------------------------------------------------- |
| `notebooks/`    | Numbered notebooks: setup, data audit, preprocessing, modelling, evaluation  |
| `src/`          | Reusable Python functions imported by the notebooks                          |
| `data/`         | Dataset documentation and (untracked) local data                             |
| `reports/`      | Final report and figures                                                     |
| `ASSISTANCE.md` | Declaration of external code, collaboration, generative AI and assistant use |

## Milestones

| Milestone            | Due            | Deliverable                                                         |
| -------------------- | -------------- | ------------------------------------------------------------------- |
| 1. Project proposal  | End of Week 3  | One-page proposal: dataset, task, target, metrics, risks            |
| 2. Data and baseline | End of Week 7  | Data audit, preprocessing, evaluation design, baseline results      |
| 3. Model comparison  | End of Week 10 | Baseline vs ≥2 learned models, plus error analysis                  |
| 4. Final portfolio   | End of Week 12 | Code, 3,000-word report, README, demo video, assistance declaration |

## Status

Milestone 1 (proposal) submitted. Working towards Milestone 2: the acquisition notebook and the
labelling pipeline are in place; the data audit, train/test design and baseline notebooks are next.
