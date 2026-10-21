"""Retrieve Chess.com games and build the per-game index.

Raw archives are cached as JSON under ``data/raw/`` so re-running the notebook
does not re-fetch months that have already been downloaded. Nothing under
``data/`` is committed - it is generated and reproducible from the public API -
so only the documentation in ``data/README.md`` is tracked.
"""

from __future__ import annotations

import io
import json
import re
import time
from pathlib import Path

import chess.pgn
import pandas as pd
import requests

from . import config

_CLOCK_RE = re.compile(r"\[%clk ")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": config.USER_AGENT})
    return session


def get_json(url: str, *, session: requests.Session | None = None, tries: int = 4) -> dict:
    """GET a JSON document, backing off on rate limits and server errors."""
    session = session or _session()
    for attempt in range(tries):
        response = session.get(url, timeout=30)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(2.0 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"gave up after {tries} attempts: {url}")


def archive_month(url: str) -> str:
    """``.../games/2026/09`` becomes ``"2026-09"``."""
    year, month = url.rsplit("/", 2)[-2:]
    return f"{year}-{month}"


def list_archives(username: str = config.USERNAME, **kwargs) -> list[str]:
    """Monthly archive URLs for a player, oldest first, up to ``config.END_MONTH``."""
    url = f"{config.API_BASE}/{username}/games/archives"
    archives = get_json(url, **kwargs)["archives"]
    return [archive for archive in archives if archive_month(archive) <= config.END_MONTH]


def download_archives(
    archives: list[str],
    raw_dir: Path = config.RAW_DIR,
    *,
    pause: float = 0.8,
) -> pd.DataFrame:
    """Cache each monthly archive as ``YYYY-MM.json``.

    Months already on disk are read rather than re-fetched, so this is safe to
    re-run. Returns one row per month describing what happened.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for url in archives:
        month = archive_month(url)
        path = raw_dir / f"{month}.json"
        already_cached = path.exists()

        if already_cached:
            payload = json.loads(path.read_text())
        else:
            payload = get_json(url)
            path.write_text(json.dumps(payload))
            time.sleep(pause)

        rows.append(
            {
                "month": month,
                "games": len(payload.get("games", [])),
                "fetched": not already_cached,
            }
        )

    return pd.DataFrame(rows)


def load_games(raw_dir: Path = config.RAW_DIR) -> list[dict]:
    """Every game object across every cached archive up to ``config.END_MONTH``."""
    games: list[dict] = []
    for path in sorted(raw_dir.glob("*.json")):
        if path.stem > config.END_MONTH:
            continue
        games.extend(json.loads(path.read_text()).get("games", []))
    return games


def ply_count(pgn: str) -> int:
    """Number of half-moves in a PGN, or 0 if it cannot be parsed."""
    if not pgn.strip():
        return 0
    try:
        parsed = chess.pgn.read_game(io.StringIO(pgn))
    except Exception:  # noqa: BLE001 - one malformed PGN should not stop the run
        return 0
    if parsed is None:
        return 0
    return sum(1 for _ in parsed.mainline_moves())


def games_overview(games: list[dict]) -> pd.DataFrame:
    """Lightweight per-game table for inspecting the raw data.

    Reads only the JSON fields, so it stays fast on the full archive set.
    """
    return pd.DataFrame(
        [
            {
                "game_id": game.get("uuid"),
                "end_time": pd.to_datetime(game.get("end_time"), unit="s", utc=True),
                "time_class": game.get("time_class"),
                "time_control": game.get("time_control"),
                "rules": game.get("rules"),
                "rated": bool(game.get("rated")),
                "has_clock": bool(_CLOCK_RE.search(game.get("pgn") or "")),
            }
            for game in games
        ]
    )


def exclude_reason(game: dict, *, username: str = config.USERNAME) -> str | None:
    """Why a game falls outside the scope, or ``None`` if it is in scope.

    Deliberately simple: these are scope decisions, not data cleaning. Games
    that pass here but have nothing to label - a PGN with no moves at all - are
    caught separately in :func:`build_game_index`.
    """
    if config.RATED_ONLY and not game.get("rated"):
        return "unrated"
    if game.get("rules") not in config.RULES:
        return f"variant:{game.get('rules')}"
    if game.get("time_class") not in config.TIME_CLASSES:
        return f"time_class:{game.get('time_class')}"
    if not (game.get("pgn") or "").strip():
        return "no_pgn"
    return None


def _index_row(game: dict, username: str) -> dict:
    """Flatten one in-scope game into an index row."""
    white = game.get("white") or {}
    black = game.get("black") or {}
    pgn = game.get("pgn") or ""
    i_am_white = str(white.get("username", "")).lower() == username.lower()
    mine, theirs = (white, black) if i_am_white else (black, white)

    return {
        "game_id": game.get("uuid"),
        "url": game.get("url"),
        "end_time": pd.to_datetime(game.get("end_time"), unit="s", utc=True),
        "time_class": game.get("time_class"),
        "time_control": game.get("time_control"),
        "rules": game.get("rules"),
        "rated": bool(game.get("rated")),
        "eco": game.get("eco"),
        "colour": "white" if i_am_white else "black",
        "my_result": mine.get("result"),
        "my_rating": mine.get("rating"),
        "opponent": theirs.get("username"),
        "opponent_rating": theirs.get("rating"),
        "rating_diff": (mine.get("rating") or 0) - (theirs.get("rating") or 0),
        "plies": ply_count(pgn),
        "clk_comments": len(_CLOCK_RE.findall(pgn)),
    }


def build_game_index(
    games: list[dict],
    *,
    username: str = config.USERNAME,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split games into an in-scope index and an excluded table.

    Returns ``(kept, excluded)``. ``excluded`` carries only enough detail to
    report why games were dropped.
    """
    kept_rows: list[dict] = []
    excluded_rows: list[dict] = []

    for game in games:
        reason = exclude_reason(game, username=username)
        row = None
        if reason is None:
            row = _index_row(game, username)
            # A PGN that parses to zero plies is a game abandoned before the
            # first move: nothing to label, and no clock data either.
            if row["plies"] == 0:
                reason = "no_moves"

        if reason is not None:
            excluded_rows.append(
                {
                    "time_class": game.get("time_class"),
                    "rules": game.get("rules"),
                    "rated": bool(game.get("rated")),
                    "exclude_reason": reason,
                }
            )
        else:
            kept_rows.append(row)

    kept = pd.DataFrame(kept_rows).sort_values("end_time").reset_index(drop=True)
    excluded = pd.DataFrame(excluded_rows)
    return kept, excluded
