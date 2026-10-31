"""Feature matrix, train/test split, cross-validation folds and baselines.

Everything a model needs to be fitted and scored on equal terms lives here, so
the baselines in Milestone 2 and the learned models in Milestone 3 see exactly
the same rows, features, folds and metrics. The choices are justified in
``notebooks/02_data_audit.ipynb``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from . import features

TARGET = "is_blunder"

# Known before the move is played. Everything else in positions.parquet is a
# key, the target, or leakage (see the audit notebook, section 7).
NUMERIC = [
    "ply",
    "pieces_white",
    "pieces_black",
    "material_diff",
    "legal_moves",
    "seconds_before",
    "my_rating_pre",
    "cp_before",
    "win_before",
    "tc_base",
    "tc_increment",
]
CATEGORICAL = ["game_stage", "mover"]

LEAKAGE = [
    "seconds_spent",
    "seconds_remaining",
    "cp_after",
    "cp_loss",
    "win_after",
    "win_loss",
    "mate_sequence",
    "mate_involved",
]

TEST_FRACTION = 0.2
N_FOLDS = 5
SEED = 0


def modelling_table(positions: pd.DataFrame) -> pd.DataFrame:
    """The author's own moves, with the time control split into two numbers.

    The target is the author's blunders, so the opponents' moves are dropped.
    ``time_control`` is a string such as ``"900+10"``; base time and increment
    are what a model can use.
    """
    table = positions[positions.is_my_move].copy()
    parsed = table.time_control.map(features.parse_time_control)
    table["tc_base"] = parsed.str[0]
    table["tc_increment"] = parsed.str[1]
    return table.reset_index(drop=True)


def time_split(table: pd.DataFrame, test_fraction: float = TEST_FRACTION) -> pd.Series:
    """``True`` for rows in the most recent ``test_fraction`` of games.

    The split is by game, not by row, so a game's moves are never on both sides.
    """
    order = table.groupby("game_id").end_time.first().sort_values().index
    cut = int(len(order) * (1 - test_fraction))
    return table.game_id.isin(order[cut:])


def cv_folds(train: pd.DataFrame, n_folds: int = N_FOLDS, seed: int = SEED):
    """Grouped folds over the training rows: no game is split across folds."""
    splitter = GroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    return list(splitter.split(train, train[TARGET], groups=train.game_id))


def make_preprocessor(scale: bool = True) -> ColumnTransformer:
    """Median-impute and scale the numeric columns, one-hot the categorical ones.

    Fitted inside each training fold, never on the full table, so the median
    and scaling statistics carry nothing from validation or test games. The only
    gap in the features is ``my_rating_pre`` for the first game in the dataset.
    """
    numeric_steps = [SimpleImputer(strategy="median")]
    if scale:
        numeric_steps.append(StandardScaler())
    return ColumnTransformer(
        [
            ("numeric", make_pipeline(*numeric_steps), NUMERIC),
            ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ]
    )


def score(y_true, risk) -> dict:
    """The three metrics fixed in the evaluation design, plus the base rate.

    PR-AUC is primary; its no-skill value is the base rate, so the two are
    reported together.
    """
    return {
        "pr_auc": average_precision_score(y_true, risk),
        "roc_auc": roc_auc_score(y_true, risk),
        "brier": brier_score_loss(y_true, risk),
        "base_rate": float(np.mean(y_true)),
    }


def cross_validate(model, train: pd.DataFrame, folds) -> pd.DataFrame:
    """Fit on each training fold, score on its validation fold; one row per fold."""
    rows = []
    for i, (fit_idx, val_idx) in enumerate(folds):
        fit, val = train.iloc[fit_idx], train.iloc[val_idx]
        model.fit(fit, fit[TARGET])
        rows.append({"fold": i, **score(val[TARGET], model.predict_proba(val)[:, 1])})
    return pd.DataFrame(rows).set_index("fold")


class BaseRate:
    """Gives every move the training blunder rate. The floor any model must beat."""

    def fit(self, X: pd.DataFrame, y) -> BaseRate:
        self.rate_ = float(np.mean(y))
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        risk = np.full(len(X), self.rate_)
        return np.column_stack([1 - risk, risk])


LEGAL_MOVE_BINS = [0, 10, 20, 30, 40, 50, np.inf]


class StageComplexityRate:
    """Blunder rate looked up by game stage and number of legal moves.

    A table of training-set rates, one per (stage, legal-moves bucket) cell,
    with no learned weights: it asks how far position complexity alone gets
    you. A cell with no training moves falls back to the overall rate.
    """

    def _cells(self, X: pd.DataFrame) -> pd.Series:
        bucket = pd.cut(X.legal_moves, LEGAL_MOVE_BINS).astype(str)
        return X.game_stage.astype(str) + " | " + bucket

    def fit(self, X: pd.DataFrame, y) -> StageComplexityRate:
        y = pd.Series(np.asarray(y, dtype=float), index=X.index)
        self.overall_ = float(y.mean())
        self.table_ = y.groupby(self._cells(X)).mean()
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        risk = self._cells(X).map(self.table_).fillna(self.overall_).to_numpy()
        return np.column_stack([1 - risk, risk])
