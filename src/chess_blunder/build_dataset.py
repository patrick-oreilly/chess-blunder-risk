"""Build the per-position modelling table: one row per ply, features plus label.

Workers run several *single-threaded* Stockfish processes in parallel. The
parallelism is across positions, never inside a search: raising ``Threads`` makes
the engine non-deterministic. Every position is also searched from an empty hash
(see ``labelling.evaluate_position``), so a label does not depend on which worker
evaluated it or in what order.

Results are checkpointed one game per line, so an interrupted run resumes rather
than starting over. A game that fails is recorded with its error and retried on
the next run; it does not stop the worker.

Usage::

    PYTHONPATH=src .venv/bin/python -m chess_blunder.build_dataset --workers 8
    PYTHONPATH=src .venv/bin/python -m chess_blunder.build_dataset --limit 8
    PYTHONPATH=src .venv/bin/python -m chess_blunder.build_dataset --finalise-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import chess
import chess.engine
import pandas as pd

from . import acquisition, config, features, labelling

SHARD_DIR = config.PROCESSED_DIR / "shards"
OUT_PARQUET = config.PROCESSED_DIR / "positions.parquet"
INDEX_CSV = config.PROCESSED_DIR / "games_index.csv"
PROGRESS_EVERY = 25


def build_rows(meta: dict, pgn: str, engine: chess.engine.SimpleEngine) -> list[dict]:
    """One row per ply for a single game: board state, clock, and label.

    Rows are produced for both players. The target is the author's own blunders,
    so ``is_my_move`` marks the rows that belong in the modelling table and the
    opponent's rows stay available as context.

    Raises ``ValueError`` if the game does not label in full, so a partly parsed
    game is never checkpointed as done.
    """
    boards = labelling.game_boards(pgn)
    labels = labelling.label_boards(boards, engine)
    if len(labels) != meta["plies"]:
        raise ValueError(f"labelled {len(labels)} plies, index says {meta['plies']}")

    clocks = features.clock_per_ply(pgn)
    base, increment = features.parse_time_control(meta.get("time_control"))

    colour = meta.get("colour")
    if not isinstance(colour, str) or colour not in ("white", "black"):
        raise ValueError(f"unusable colour {colour!r} for game {meta.get('game_id')}")
    my_colour = chess.WHITE if colour == "white" else chess.BLACK

    # The mover's clock after their own previous move. Before a player's first
    # move their clock is the base time; after that it is whatever the last
    # %clk comment said, or None if that comment was missing - so a gap makes
    # the next think time unknown rather than spanning two moves.
    last_clock: dict[chess.Color, float | None] = {chess.WHITE: None, chess.BLACK: None}
    has_moved = {chess.WHITE: False, chess.BLACK: False}

    rows: list[dict] = []
    for label, board in zip(labels, boards):
        remaining = clocks[label.ply - 1] if label.ply - 1 < len(clocks) else None
        before = last_clock[board.turn] if has_moved[board.turn] else float(base)
        spent = features.think_time(remaining, last_clock[board.turn], increment)
        last_clock[board.turn] = remaining
        has_moved[board.turn] = True

        mine = features.material_points(board, my_colour)
        theirs = features.material_points(board, not my_colour)

        rows.append(
            {
                "game_id": meta["game_id"],
                "ply": label.ply,
                "mover": label.mover,
                "is_my_move": (board.turn == chess.WHITE) == (my_colour == chess.WHITE),
                "pieces_white": features.piece_count(board, chess.WHITE),
                "pieces_black": features.piece_count(board, chess.BLACK),
                "material_diff": mine - theirs,
                "legal_moves": board.legal_moves.count(),
                "game_stage": features.game_stage(label.ply, mine + theirs),
                # Known before the move: the clock as the mover sits down to it.
                "seconds_before": before,
                # Known only after the move: for the think-time analysis, not
                # for a model predicting the move.
                "seconds_remaining": remaining,
                "seconds_spent": spent,
                "my_rating_pre": meta.get("my_rating_pre"),
                "time_control": meta.get("time_control"),
                "eco": meta.get("eco"),
                "end_time": meta.get("end_time"),
                "cp_before": label.cp_before,
                "cp_after": label.cp_after,
                "cp_loss": label.cp_loss,
                # Rounded for storage only; the label was judged unrounded.
                "win_before": round(label.win_before, 2),
                "win_after": round(label.win_after, 2),
                "win_loss": round(label.win_loss, 2),
                "is_blunder": label.is_blunder,
                "mate_sequence": label.mate_sequence,
                "mate_involved": label.mate_involved,
            }
        )
    return rows


def shard_path(worker_id: int, shard_dir: Path = SHARD_DIR) -> Path:
    return shard_dir / f"labels-{worker_id:02d}.jsonl"


def shard_records(shard_dir: Path = SHARD_DIR) -> tuple[list[dict], int]:
    """Every parsed record across the shards, plus any lines that would not parse.

    A line only fails to parse if a run was killed while writing it, so the
    count is surfaced rather than swallowed.
    """
    records: list[dict] = []
    skipped = 0
    for path in sorted(shard_dir.glob("labels-*.jsonl")):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if isinstance(record, dict) and "game_id" in record:
                records.append(record)
            else:
                skipped += 1
    return records, skipped


def completed_game_ids(shard_dir: Path = SHARD_DIR) -> set[str]:
    """Games already checkpointed successfully. Failed games are retried."""
    records, skipped = shard_records(shard_dir)
    if skipped:
        print(f"warning: ignored {skipped} unparseable shard line(s)", file=sys.stderr)
    return {record["game_id"] for record in records if "error" not in record}


def add_pre_game_rating(index: pd.DataFrame) -> pd.DataFrame:
    """Add ``my_rating_pre``: the author's rating going into each game.

    Chess.com archives record the rating *after* the game, which encodes the
    game's result and so leaks into a blunder model. The rating going into a
    game is the rating after the previous one. Every game in the index is rated
    and rapid, so they share one rating pool; the first game has no previous
    rating and gets NaN.
    """
    index = index.sort_values("end_time").reset_index(drop=True)
    index["my_rating_pre"] = index["my_rating"].shift(1)
    return index


def is_partial_line(path: Path) -> bool:
    """True if a shard ends mid-line, i.e. a previous run was killed writing it."""
    if not path.exists() or not path.stat().st_size:
        return False
    with path.open("rb") as handle:
        handle.seek(-1, os.SEEK_END)
        return handle.read(1) != b"\n"


def process_chunk(
    worker_id: int,
    payload: list[tuple[dict, str]],
    shard_dir: Path = SHARD_DIR,
) -> tuple[int, int]:
    """Label one worker's share of the games, writing after every game."""
    engine = labelling.open_engine()
    path = shard_path(worker_id, shard_dir)
    games_done = rows_done = 0

    try:
        with path.open("a") as handle:
            if is_partial_line(path):
                # A previous run was killed mid-write. Close the partial line off
                # so this run's records start cleanly. The orphaned line will not
                # parse, so its game is simply labelled again.
                handle.write("\n")
            for meta, pgn in payload:
                try:
                    rows = build_rows(meta, pgn, engine)
                except Exception as exc:  # noqa: BLE001 - one bad game must not stop the worker
                    if isinstance(exc, chess.engine.EngineTerminatedError):
                        engine = labelling.open_engine()
                    record = {"game_id": meta["game_id"], "error": f"{type(exc).__name__}: {exc}"}
                    handle.write(json.dumps(record) + "\n")
                    handle.flush()
                    print(f"  worker {worker_id}: {meta['game_id']} failed: {record['error']}",
                          file=sys.stderr, flush=True)
                    continue
                handle.write(json.dumps({"game_id": meta["game_id"], "rows": rows}) + "\n")
                handle.flush()
                games_done += 1
                rows_done += len(rows)
                if games_done % PROGRESS_EVERY == 0:
                    print(
                        f"  worker {worker_id}: {games_done}/{len(payload)} games, "
                        f"{rows_done} positions",
                        file=sys.stderr,
                        flush=True,
                    )
    finally:
        engine.quit()

    return games_done, rows_done


def run(workers: int = 8, limit: int | None = None, shard_dir: Path = SHARD_DIR) -> None:
    shard_dir.mkdir(parents=True, exist_ok=True)

    index = add_pre_game_rating(pd.read_csv(INDEX_CSV)).to_dict("records")
    by_id = {game["uuid"]: game for game in acquisition.load_games()}

    done = completed_game_ids(shard_dir)
    todo = [meta for meta in index if meta["game_id"] not in done]
    if limit is not None:
        todo = todo[:limit]

    if not todo:
        print(f"nothing to do: all {len(index)} games are already checkpointed")
        return

    plies = sum(by_id[meta["game_id"]]["pgn"].count("%clk") + 1 for meta in todo)
    print(f"games : {len(index)} in the index, {len(done)} already done, {len(todo)} to label")
    print(f"work  : about {plies} positions")
    print(f"workers: {workers}")

    chunks: list[list[tuple[dict, str]]] = [[] for _ in range(workers)]
    for position, meta in enumerate(todo):
        chunks[position % workers].append((meta, by_id[meta["game_id"]]["pgn"]))

    started = time.perf_counter()
    total_games = total_rows = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(process_chunk, worker_id, chunk, shard_dir)
            for worker_id, chunk in enumerate(chunks)
            if chunk
        ]
        for future in as_completed(futures):
            games_done, rows_done = future.result()
            total_games += games_done
            total_rows += rows_done

    elapsed = time.perf_counter() - started
    print(f"labelled {total_games} games / {total_rows} positions in {elapsed / 60:.1f} min")


def finalise(shard_dir: Path = SHARD_DIR, out_path: Path = OUT_PARQUET) -> pd.DataFrame:
    """Combine the shards into a single table, and report what is missing.

    Games that failed, or that were never labelled, are listed rather than
    silently absent, so the data audit can account for every game in the index.
    """
    checkpointed, skipped = shard_records(shard_dir)
    if skipped:
        print(f"warning: ignored {skipped} unparseable shard line(s)")

    done = {record["game_id"] for record in checkpointed if "error" not in record}
    failed = {
        record["game_id"]: record["error"]
        for record in checkpointed
        if "error" in record and record["game_id"] not in done
    }
    index_ids = set(pd.read_csv(INDEX_CSV, usecols=["game_id"])["game_id"])
    missing = index_ids - done - set(failed)
    print(f"games: {len(done)} labelled, {len(failed)} failed, {len(missing)} not yet labelled")
    for game_id, error in sorted(failed.items()):
        print(f"  failed {game_id}: {error}")

    records = [
        row
        for record in checkpointed
        if "error" not in record
        for row in record.get("rows") or []
    ]
    if not records:
        raise SystemExit("no checkpointed rows found")

    frame = pd.DataFrame(records)
    # Chunk assignment changes if the run is restarted with a different worker
    # count, so make "one row per ply" explicit rather than assumed.
    before = len(frame)
    frame = frame.drop_duplicates(subset=["game_id", "ply"])
    if len(frame) < before:
        print(f"warning: dropped {before - len(frame)} duplicate rows")
    frame["end_time"] = pd.to_datetime(frame["end_time"], utc=True)
    frame = frame.sort_values(["end_time", "game_id", "ply"]).reset_index(drop=True)
    frame.to_parquet(out_path, index=False)

    print(
        f"wrote {out_path}: "
        f"{len(frame)} rows, {frame.shape[1]} columns"
    )
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8, help="parallel engine processes")
    parser.add_argument("--limit", type=int, default=None, help="only label this many games")
    parser.add_argument("--finalise-only", action="store_true", help="skip labelling, just combine")
    args = parser.parse_args()

    if not args.finalise_only:
        run(workers=args.workers, limit=args.limit)
    finalise()


if __name__ == "__main__":
    main()
