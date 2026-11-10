"""Feature matrix, train/test split, cross-validation folds and baselines.

Everything a model needs to be fitted and scored on equal terms lives here, so
the baselines in Milestone 2 and the learned models in Milestone 3 see exactly
the same rows, features, folds and metrics. The choices are justified in
``notebooks/02_data_audit.ipynb``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold, ParameterGrid
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, SplineTransformer, StandardScaler

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

# The engine's view of the position. Blunder risk is near zero in decided
# positions at either end and peaks where one side is clearly but not decisively
# ahead, with a dip at dead level: a shape a linear model can only fit if these
# columns are expanded into splines first.
SPLINE = ["cp_before", "win_before"]

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


def make_preprocessor(scale: bool = True, spline: bool = False) -> ColumnTransformer:
    """Median-impute and scale the numeric columns, one-hot the categorical ones.

    Fitted inside each training fold, never on the full table, so the median
    and scaling statistics carry nothing from validation or test games. The only
    gap in the features is ``my_rating_pre`` for the first game in the dataset.

    With ``spline``, the ``SPLINE`` columns become cubic splines with knots at
    quantiles instead, so a linear model can bend with them. Tree models split
    on raw values and do not need it.
    """
    numeric_steps = [SimpleImputer(strategy="median")]
    if scale:
        numeric_steps.append(StandardScaler())
    linear = [c for c in NUMERIC if not (spline and c in SPLINE)]
    transformers = [
        ("numeric", make_pipeline(*numeric_steps), linear),
        ("categorical", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ]
    if spline:
        transformers.append(("spline", SplineTransformer(n_knots=5, knots="quantile"), SPLINE))
    return ColumnTransformer(transformers)


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


def out_of_fold(model, train: pd.DataFrame, folds) -> tuple[pd.DataFrame, np.ndarray]:
    """Fit on each training fold, score on its validation fold.

    Returns the scores, one row per fold, and the out-of-fold risk for every
    training row: each row's prediction comes from the one model that did not
    see its game. Plots and error analysis are built on these predictions.

    Each fold also records ``train_pr_auc``, the model scored on the rows it was
    fitted on. A large gap between that and the validation PR-AUC means the
    model is memorising training games rather than learning what carries over.
    """
    rows, oof = [], np.zeros(len(train))
    for i, (fit_idx, val_idx) in enumerate(folds):
        fit, val = train.iloc[fit_idx], train.iloc[val_idx]
        model.fit(fit, fit[TARGET])
        oof[val_idx] = model.predict_proba(val)[:, 1]
        train_pr_auc = average_precision_score(fit[TARGET], model.predict_proba(fit)[:, 1])
        rows.append({"fold": i, **score(val[TARGET], oof[val_idx]), "train_pr_auc": train_pr_auc})
    return pd.DataFrame(rows).set_index("fold"), oof


def cross_validate(model, train: pd.DataFrame, folds) -> pd.DataFrame:
    """Fit on each training fold, score on its validation fold; one row per fold."""
    return out_of_fold(model, train, folds)[0]


@dataclass
class TuningResult:
    """What ``tune`` found: every setting's scores, the winner, and its predictions."""

    results: pd.DataFrame  # one row per setting: its parameters, then mean and std of each metric
    best_params: dict
    fold_scores: pd.DataFrame  # the winning setting's scores, one row per fold
    oof: np.ndarray  # out-of-fold risk from the winning setting


def tune(make_model, grid: dict, train: pd.DataFrame, folds) -> TuningResult:
    """Cross-validate every setting in ``grid`` and keep the best by mean PR-AUC.

    ``make_model`` builds a fresh model from keyword arguments; ``grid`` maps
    each argument to the values to try. Only training rows come in, so the
    test set plays no part in choosing a setting. The best mean wins outright:
    with five folds, differences smaller than the fold std are noise, and the
    results table shows them so they can be read that way.
    """
    rows, best = [], None
    for params in ParameterGrid(grid):
        scores, oof = out_of_fold(make_model(**params), train, folds)
        summary = scores.drop(columns="base_rate").agg(["mean", "std"])
        rows.append({**params, **{f"{s} {m}": summary.at[s, m] for m in summary.columns for s in summary.index}})
        if best is None or summary.at["mean", "pr_auc"] > best[0]:
            best = (summary.at["mean", "pr_auc"], params, scores, oof)
    return TuningResult(pd.DataFrame(rows), *best[1:])


def fold_differences(a: pd.DataFrame, b: pd.DataFrame, metric: str = "pr_auc") -> pd.DataFrame:
    """Two models' fold scores side by side, with ``b - a`` for each fold.

    Both models were scored on the same folds, so a fold that is hard for one
    is hard for both; differencing fold by fold cancels that out. The rule set
    in the notebook: ``b`` beats ``a`` only if it wins on every fold.
    """
    return pd.DataFrame({"a": a[metric], "b": b[metric], "b - a": b[metric] - a[metric]})


def logistic_regression(C: float) -> Pipeline:
    """Logistic regression behind the spline preprocessor.

    No class weights: reweighting would inflate every predicted risk and spoil
    the Brier score and reliability plot, for little change in how moves are
    ranked, which is what PR-AUC measures.
    """
    return make_pipeline(make_preprocessor(spline=True), LogisticRegression(C=C, max_iter=1000))


def gradient_boosting(max_iter: int, learning_rate: float, min_samples_leaf: int) -> Pipeline:
    """Histogram gradient boosting behind the preprocessor, without scaling or splines.

    Trees split on raw values, so they bend with curved effects by themselves.
    Early stopping is off: its internal validation split picks rows at random,
    not whole games, so it would check itself on games it has partly seen. The
    number of trees is tuned on the grouped folds instead.
    """
    model = HistGradientBoostingClassifier(
        max_iter=max_iter,
        learning_rate=learning_rate,
        min_samples_leaf=min_samples_leaf,
        early_stopping=False,
        random_state=SEED,
    )
    return make_pipeline(make_preprocessor(scale=False), model)


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
