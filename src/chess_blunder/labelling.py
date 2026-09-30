"""Label positions with Stockfish to produce the blunder target.

A blunder is a move that drops the engine evaluation by at least
``BLUNDER_CP`` centipawns. The engine is driven at the settings recorded in
``data/README.md`` so a re-run reproduces the same labels.

Cost note: at the agreed 100,000 nodes, single-threaded, Stockfish 19 evaluates
a position in about 0.29s. One evaluation per position is reused for the move
that follows it, so a game of *k* plies costs *k + 1* evaluations rather than
*2k*. Labelling all 260,030 plies is therefore a ~21 hour job.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import chess
import chess.engine
import chess.pgn

DEFAULT_ENGINE = "/opt/homebrew/bin/stockfish"
NODES = 100_000
THREADS = 1
HASH_MB = 16
BLUNDER_CP = 200
MATE_CLAMP = 1000


@dataclass(frozen=True)
class MoveLabel:
    """One played move and what the engine thought before and after it."""

    ply: int
    mover: str
    cp_before: int
    cp_after: int
    cp_loss: int

    @property
    def is_blunder(self) -> bool:
        return self.cp_loss >= BLUNDER_CP

    def blunder_at(self, threshold: int) -> bool:
        return self.cp_loss >= threshold


def open_engine(path: str = DEFAULT_ENGINE) -> chess.engine.SimpleEngine:
    """Start Stockfish with the project's fixed settings."""
    engine = chess.engine.SimpleEngine.popen_uci(path)
    engine.configure({"Threads": THREADS, "Hash": HASH_MB})
    return engine


def game_boards(pgn: str) -> list[chess.Board]:
    """Every position in a game, including the one after the final move."""
    parsed = chess.pgn.read_game(io.StringIO(pgn))
    if parsed is None:
        return []

    boards = []
    board = parsed.board()
    boards.append(board.copy(stack=False))
    for move in parsed.mainline_moves():
        board.push(move)
        boards.append(board.copy(stack=False))
    return boards


def score_white(board: chess.Board, engine: chess.engine.SimpleEngine) -> int:
    """Evaluation of a position in centipawns from White's point of view.

    Terminal positions are scored directly rather than sent to the engine, and
    mate scores are clamped to ``MATE_CLAMP`` so that a forced mate does not
    swamp the centipawn-drop arithmetic.
    """
    if board.is_checkmate():
        return -MATE_CLAMP if board.turn == chess.WHITE else MATE_CLAMP
    if board.is_game_over():
        return 0

    info = engine.analyse(board, chess.engine.Limit(nodes=NODES))
    return info["score"].pov(chess.WHITE).score(mate_score=MATE_CLAMP)


def label_game(pgn: str, engine: chess.engine.SimpleEngine) -> list[MoveLabel]:
    """Centipawn loss for every move in a game.

    Each position is evaluated once and reused: the value before move *i* is
    the value of position *i*, and the value after it is the value of position
    *i + 1*. That halves the number of engine calls compared with evaluating
    every move twice.
    """
    boards = game_boards(pgn)
    if len(boards) < 2:
        return []

    scores = [score_white(board, engine) for board in boards]

    labels = []
    for ply, board in enumerate(boards[:-1]):
        mover_is_white = board.turn == chess.WHITE
        before, after = scores[ply], scores[ply + 1]
        loss = (before - after) if mover_is_white else (after - before)
        labels.append(
            MoveLabel(
                ply=ply + 1,
                mover="white" if mover_is_white else "black",
                cp_before=before,
                cp_after=after,
                cp_loss=loss,
            )
        )
    return labels
