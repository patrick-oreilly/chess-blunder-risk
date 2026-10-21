"""Per-position features read off the board and the game record.

Everything here is a pure function of a position or a PGN fragment, so it can be
reasoned about (and tested) without starting an engine.
"""

from __future__ import annotations

import io
import re

import chess
import chess.pgn

PIECE_POINTS = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}

# Heuristics for game stage. Both are choices rather than facts, so they are
# stated here and in data/README.md instead of being buried in the analysis.
OPENING_PLIES = 20
ENDGAME_MATERIAL = 20

_CLK_RE = re.compile(r"\[%clk ([\d:.]+)\]")


def material_points(board: chess.Board, colour: chess.Color) -> int:
    """Standard piece values held by one side."""
    return sum(
        PIECE_POINTS.get(piece.piece_type, 0)
        for piece in board.piece_map().values()
        if piece.color == colour
    )


def piece_count(board: chess.Board, colour: chess.Color) -> int:
    """Number of pieces (including pawns) held by one side."""
    return sum(1 for piece in board.piece_map().values() if piece.color == colour)


def game_stage(ply: int, total_material: int) -> str:
    """``opening`` / ``middlegame`` / ``endgame`` from ply and total material."""
    if ply <= OPENING_PLIES:
        return "opening"
    if total_material <= ENDGAME_MATERIAL:
        return "endgame"
    return "middlegame"


def parse_time_control(raw: str | None) -> tuple[int, int]:
    """``"900+10"`` becomes ``(900, 10)`` - base seconds, then increment."""
    if not raw:
        return 0, 0
    base, _, increment = str(raw).partition("+")
    try:
        return int(base), int(increment or 0)
    except ValueError:
        return 0, 0


def clock_seconds(text: str) -> float | None:
    """``"0:09:56.3"`` becomes ``596.3``."""
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def clock_per_ply(pgn: str) -> list[float | None]:
    """Seconds remaining after each move, in ply order.

    Read from the ``%clk`` comments rather than inferred. For rapid games the
    comment is a genuine countdown, which is what makes think time derivable at
    all; for daily games it is not, which is why those games are out of scope.
    """
    game = chess.pgn.read_game(io.StringIO(pgn))
    if game is None:
        return []

    clock = []
    for node in game.mainline():
        match = _CLK_RE.search(node.comment or "")
        clock.append(clock_seconds(match.group(1)) if match else None)
    return clock


def think_time(
    clock_after: float | None,
    previous: float | None,
    increment: int,
) -> float | None:
    """Seconds spent on a move: the drop in the mover's own clock.

    ``previous`` is the mover's clock after their own last move, or ``None`` for
    their first move of the game. It is left as ``None`` rather than assumed to
    be the base time, because Chess.com's first clock comment for a colour is
    sometimes the base time and sometimes a genuine post-move value - so a
    first-move think time cannot be recovered reliably and is not guessed at.
    """
    if clock_after is None or previous is None:
        return None
    return round(previous + increment - clock_after, 1)
