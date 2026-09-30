# Chess Blunder Risk

Can a machine learning model predict whether a player will make a major tactical blunder on their
next move?

**CT4101 Machine Learning — Portfolio Project**
Patrick O'Reilly — 23366866

## The prediction task

Binary classification: **will the next move be a blunder?**

A blunder is defined as a move that drops the engine evaluation by **200 centipawns or more**
(roughly two pawns). That threshold is a choice, not a fact, changing it changes every reported
figure, so it is stated up front rather than buried.

The secondary question whether thinking time still predicts blunders once position difficulty is
accounted for carries the most interpretation risk, because a naive reading of it suggests "play
faster", which is not advice this project supports.

## Data

4,373 games from my own Chess.com account via the free Published-Data API, filtered to 4,008 usable
rapid games, labelled locally with Stockfish 19. 260,030 plies, so roughly 260,000 board positions.

Source, licence and preparation steps are in [`data/README.md`](data/README.md). **The raw data is not
committed to this repository**, see that file for why.

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

Scaffold only at the moment
