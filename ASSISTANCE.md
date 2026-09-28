# Assistance Declaration

The CT4101 brief requires that external code, collaboration, generative AI and coding-assistant use be
declared, and that all assisted work be verified. An assistance declaration is a required deliverable
at **Milestones 2, 3 and 4** (not Milestone 1).

The rule from the module's AI guidance: assistance is permitted; submitting AI-produced work as your
own is not. The bar from the brief is that you _"must be able to explain all submitted code, results
and decisions"_, and that suspicious cases may lead to a student interview.

Keep this file updated as you go. Reconstructing it at the end is the failure mode.

## Log

| Date       | What                            | Tool           | How it was used                                                                                             | Verified by |
| ---------- | ------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------- | ----------- |
| 2026-09-21 | Repository scaffold             | GitHub Copilot | Drafted `README.md`, `requirements.txt`, `.gitignore`, `data/README.md` and this file                       |             |
| 2026-09-21 | Milestone 1 proposal formatting | GitHub Copilot | Reformatted hand-written proposal text into Markdown; added the dataset/engine citations the brief requires |             |

**Action for the author:** review the rows above, correct anything inaccurate, and describe how each
piece of assisted work was checked. A blank "Verified by" column is an unfinished declaration.

## External code and tools

The brief asks for external code to be declared alongside AI assistance. The target variable is
produced by a third-party engine, so the components that shape the results are listed here.

| Component                | Version | Licence      | Role                                             |
| ------------------------ | ------- | ------------ | ------------------------------------------------ |
| Stockfish                | 19      | GPL-3.0-only | Engine evaluations that define the blunder label |
| python-chess             | 1.11.2  | GPL-3.0+     | PGN parsing, board state, legal-move counts      |
| stockfish (PyPI wrapper) | 5.2.0   | MIT          | Python interface to the engine binary            |
| scikit-learn             | 1.9.1   | BSD-3-Clause | Models and metrics                               |
| pandas                   | 3.0.6   | BSD-3-Clause | Tabular data handling                            |
| numpy                    | 2.5.3   | BSD-3-Clause | Numerical operations                             |

The Stockfish binary is installed with Homebrew and pinned (`brew pin stockfish`) so it cannot
upgrade part-way through the project and silently change the labels. Python package versions are
recorded in `requirements.txt`; the engine path and evaluation settings are recorded in
`data/README.md`.

## What still needs deciding

- Whether the Milestone 1 proposal belongs in this public repository at all (see the note in the
  conversation about publishing a submission draft before it is marked).
- Whether each assisted use is _substantive_ (shaped the analysis or the code) or _editorial_
  (formatting, citations). The brief asks about both, but they carry different weight.
