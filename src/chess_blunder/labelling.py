"""Label positions with Stockfish to produce the blunder target.

A blunder is judged with Lichess's move-judgement rules (lila,
``modules/tree/src/main/Advice.scala``), so the definition can be cited rather
than invented:

- **Ordinary score to ordinary score.** Each score is turned into winning
  chances with Lichess's logistic curve, after clamping it to +/-1000cp
  (``ui/lib/src/ceval/winningChances.ts``). A drop of 0.3 on Lichess's -1..1
  scale - 15 percentage points of win probability - is a blunder.
- **A forced mate on either side of the move.** The curve is not used. Moving
  into a forced mate against you is a blunder unless you were already at -700cp
  or worse ("mate created"). Throwing away your own forced mate is a blunder
  unless you are still at +700cp or better afterwards ("mate lost"). Every other
  mate transition carries no judgement.

Win probability rather than raw centipawns, because a centipawn drop means
different things in different positions: +150 to -150 turns a likely win into a
likely loss, while +2000 to +1360 changes nothing about the result.

Reproducibility: every position is searched from an empty hash table and with
the game's move history. The empty hash makes each evaluation a function of the
position alone - not of whichever positions the same engine process searched
before - so labels do not change with the worker count, the game order or a
resume. The move history lets the engine see repetition draws.

Cost note: at the agreed 100,000 nodes, single-threaded, Stockfish 19 evaluates
a position in about 0.3s. One evaluation per position is reused for the move
that follows it, so a game of *k* plies costs *k + 1* evaluations rather than
*2k*. Labelling all 260,030 plies is a ~21 hour job on one core, or a few hours
across eight worker processes (see ``build_dataset``).
"""

from __future__ import annotations

import io
import math
import os
import shutil
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

# Set STOCKFISH_PATH to use a binary that is not the first ``stockfish`` on PATH.
ENGINE_ENV = "STOCKFISH_PATH"
NODES = 100_000
THREADS = 1
HASH_MB = 16

# Lichess's fit of centipawns to winning chances (winningChances.ts).
WIN_SLOPE = 0.00368208
# Lichess clamps ordinary scores to this before the curve.
CP_CLAMP = 1000
# Percentage points of win probability: Lichess's 0.3 on its -1..1 scale.
BLUNDER_WIN = 15
# Lichess's mate thresholds (Advice.scala, MateAdvice).
MATE_JUDGEMENT_CP = 700

# Reported centipawn losses are capped here so a mate flip does not swamp an average.
MAX_LOSS = 1000

MATE_CREATED = "mate_created"
MATE_LOST = "mate_lost"


def engine_path() -> str:
    """The Stockfish binary: ``$STOCKFISH_PATH`` if set, else ``stockfish`` on PATH."""
    path = os.environ.get(ENGINE_ENV) or shutil.which("stockfish")
    if not path:
        raise FileNotFoundError(
            f"Stockfish not found: install it or set {ENGINE_ENV} to the binary"
        )
    return path


def open_engine(path: str | None = None) -> chess.engine.SimpleEngine:
    """Start Stockfish with the project's fixed settings."""
    engine = chess.engine.SimpleEngine.popen_uci(path or engine_path())
    engine.configure({"Threads": THREADS, "Hash": HASH_MB})
    return engine


def game_boards(pgn: str) -> list[chess.Board]:
    """Every position in a game, including the one after the final move.

    Each board keeps its move stack, so repetition can be detected and the
    engine is sent the game's history rather than a bare FEN.

    Raises ``ValueError`` if the PGN has an illegal or unparseable move: the
    parser would otherwise stop the mainline there and the game would be
    labelled only in part.
    """
    parsed = chess.pgn.read_game(io.StringIO(pgn))
    if parsed is None:
        return []
    if parsed.errors:
        raise ValueError(f"PGN did not parse cleanly: {parsed.errors[0]}")

    boards = []
    board = parsed.board()
    boards.append(board.copy())
    for move in parsed.mainline_moves():
        board.push(move)
        boards.append(board.copy())
    return boards


def win_percent(cp: float) -> float:
    """Lichess's winning chances on a 0-100 scale, from White-relative centipawns."""
    return 50 + 50 * (2 / (1 + math.exp(-WIN_SLOPE * cp)) - 1)


@dataclass(frozen=True)
class PositionEval:
    """One position's evaluation from White's point of view.

    Exactly one of ``cp`` and ``mate`` is set. ``mate`` is moves to mate, positive
    if White mates; a checkmate already on the board is ``mate=0`` with
    ``mated`` naming the side that has been mated.
    """

    cp: int | None = None
    mate: int | None = None
    mated: chess.Color | None = None

    def mate_for(self) -> chess.Color | None:
        """The side with a forced mate, or ``None``."""
        if self.mated is not None:
            return not self.mated
        if self.mate is None:
            return None
        return chess.WHITE if self.mate > 0 else chess.BLACK

    def pov_cp(self, colour: chess.Color) -> int:
        """Centipawns for ``colour``, 0 if this is a mate (Lichess's ``povCpOrZero``)."""
        if self.cp is None:
            return 0
        return self.cp if colour == chess.WHITE else -self.cp

    def win(self) -> float:
        """White's winning chances, 0-100, with Lichess's clamp and mate mapping."""
        winner = self.mate_for()
        if winner is not None:
            # Mate in n is treated as (21 - min(10, n)) * 100 centipawns, unclamped.
            cp = (21 - min(10, abs(self.mate or 0))) * 100
            return win_percent(cp if winner == chess.WHITE else -cp)
        return win_percent(max(-CP_CLAMP, min(CP_CLAMP, self.cp or 0)))

    def stored_cp(self) -> int:
        """Centipawns clamped to +/-``CP_CLAMP``, with any mate at the clamp."""
        winner = self.mate_for()
        if winner is not None:
            return CP_CLAMP if winner == chess.WHITE else -CP_CLAMP
        return max(-CP_CLAMP, min(CP_CLAMP, self.cp or 0))


def evaluate_position(board: chess.Board, engine: chess.engine.SimpleEngine) -> PositionEval:
    """Evaluate a position from White's point of view.

    Positions where the game is over are scored directly: checkmate as a mate,
    and every draw - including a claimable threefold repetition or 50-move rule,
    which Chess.com applies automatically - as level.
    """
    if board.is_checkmate():
        return PositionEval(mate=0, mated=board.turn)
    if board.is_game_over(claim_draw=True):
        return PositionEval(cp=0)

    # A fresh ``game`` object makes python-chess send ``ucinewgame``, which
    # clears the hash, so no search inherits anything from the one before it.
    info = engine.analyse(board, chess.engine.Limit(nodes=NODES), game=object())
    pov = info["score"].pov(chess.WHITE)
    if pov.is_mate():
        return PositionEval(mate=pov.mate())
    return PositionEval(cp=pov.score())


def mate_sequence(before: PositionEval, after: PositionEval, mover: chess.Color) -> str | None:
    """Lichess's mate transitions, from the mover's point of view."""
    opponent = not mover
    if before.mate_for() is None and after.mate_for() == opponent:
        return MATE_CREATED
    if before.mate_for() == mover and after.mate_for() != mover:
        return MATE_LOST
    return None


@dataclass(frozen=True)
class MoveLabel:
    """One played move and what the engine thought before and after it.

    ``cp_*`` are White-relative and clamped, for reporting. ``win_*`` are the
    mover's own winning chances, 0-100, unrounded. ``mate_sequence`` is set when
    a Lichess mate rule judged the move rather than the winning-chances drop.
    """

    ply: int
    mover: str
    cp_before: int
    cp_after: int
    cp_loss: int
    win_before: float
    win_after: float
    win_loss: float
    is_blunder: bool
    mate_sequence: str | None = None
    mate_before: bool = False
    mate_after: bool = False

    @property
    def mate_involved(self) -> bool:
        """True if a forced mate stood on the board before or after the move."""
        return self.mate_before or self.mate_after

    def blunder_at(self, threshold: float) -> bool:
        """Blunder at a different winning-chances threshold, in percentage points.

        Moves judged by a mate rule keep that judgement: the threshold only moves
        the line for ordinary-score moves.
        """
        if self.mate_sequence is not None:
            return self.is_blunder
        if self.mate_involved:
            return False
        return self.win_loss >= threshold


def judge(
    before: PositionEval,
    after: PositionEval,
    mover: chess.Color,
    win_loss: float,
) -> tuple[bool, str | None]:
    """Whether a move is a blunder under Lichess's rules, and which mate rule applied.

    ``win_loss`` is compared unrounded, so 14.996 is not a blunder.
    """
    if before.mate_for() is None and after.mate_for() is None:
        return win_loss >= BLUNDER_WIN, None

    sequence = mate_sequence(before, after, mover)
    if sequence == MATE_CREATED:
        return before.pov_cp(mover) >= -MATE_JUDGEMENT_CP, sequence
    if sequence == MATE_LOST:
        return after.pov_cp(mover) <= MATE_JUDGEMENT_CP, sequence
    return False, None


def label_boards(
    boards: list[chess.Board],
    engine: chess.engine.SimpleEngine,
) -> list[MoveLabel]:
    """Labels for every move, from parsed positions.

    This is the single definition of the label: the judgement rules, the
    winning-chances arithmetic and the mate flags all live here, so the labeller
    and the dataset builder cannot drift apart.

    Each position is evaluated once and reused: the value before move *i* is the
    value of position *i*, and the value after it is the value of position
    *i + 1*.
    """
    if len(boards) < 2:
        return []

    evals = [evaluate_position(board, engine) for board in boards]

    labels = []
    for ply, board in enumerate(boards[:-1]):
        mover = board.turn
        before, after = evals[ply], evals[ply + 1]
        cp_b, cp_a = before.stored_cp(), after.stored_cp()
        loss = (cp_b - cp_a) if mover == chess.WHITE else (cp_a - cp_b)
        # The mover's own winning chances: White's as computed, Black's mirrored.
        win_before = before.win() if mover == chess.WHITE else 100 - before.win()
        win_after = after.win() if mover == chess.WHITE else 100 - after.win()
        is_blunder, sequence = judge(before, after, mover, win_before - win_after)
        labels.append(
            MoveLabel(
                ply=ply + 1,
                mover="white" if mover == chess.WHITE else "black",
                cp_before=cp_b,
                cp_after=cp_a,
                cp_loss=min(loss, MAX_LOSS),
                win_before=win_before,
                win_after=win_after,
                win_loss=win_before - win_after,
                is_blunder=is_blunder,
                mate_sequence=sequence,
                mate_before=before.mate_for() is not None,
                mate_after=after.mate_for() is not None,
            )
        )
    return labels


def label_game(pgn: str, engine: chess.engine.SimpleEngine) -> list[MoveLabel]:
    """Labels for every move in a PGN. Wraps :func:`label_boards`."""
    return label_boards(game_boards(pgn), engine)
