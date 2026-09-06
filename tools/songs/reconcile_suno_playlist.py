#!/usr/bin/env python3
"""Reconcile a Suno playlist snapshot against semantic/songs YAML.

Dev-only tool. Does not write semantic files. Never contacts Suno unless
--fetch is passed; default reads the committed fixture.

Usage:
  python3 tools/songs/reconcile_suno_playlist.py
  python3 tools/songs/reconcile_suno_playlist.py --fixture tools/songs/fixtures/suno-playlist-2026-09-06.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required") from exc

REPO = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO / "tools" / "songs" / "fixtures" / "suno-playlist-2026-09-06.json"
PLAYLIST_API = (
    "https://studio-api.prod.suno.com/api/playlist/ac533aa1-6688-4901-833a-ec792bb21e87/?page=1"
)
NULL_UUID = "00000000-0000-0000-0000-000000000000"
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://suno.com/",
    "Origin": "https://suno.com",
}


def _norm_title(title: str) -> str:
    t = title.replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)
    t = re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    return t


def _load_snapshot(path: Path | None, *, fetch: bool) -> dict:
    if fetch:
        req = urllib.request.Request(PLAYLIST_API, headers=FETCH_HEADERS)
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return {"playlist": data, "source": PLAYLIST_API}
    fixture_path = path or DEFAULT_FIXTURE
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    if "playlist" in raw and isinstance(raw["playlist"], dict):
        return raw
    return {"playlist": raw, "source": str(fixture_path)}


def _iter_clips(snapshot: dict) -> list[dict]:
    playlist = snapshot.get("playlist") or snapshot
    clips = playlist.get("playlist_clips") or []
    out = []
    for item in clips:
        clip = item.get("clip") if isinstance(item, dict) else None
        if not isinstance(clip, dict):
            continue
        out.append(
            {
                "position": int(item.get("relative_index") or 0),
                "id": str(clip.get("id") or ""),
                "title": str(clip.get("title") or ""),
                "created_at": clip.get("created_at"),
                "metadata": clip.get("metadata") or {},
            }
        )
    return out


def _load_songs() -> dict[str, dict]:
    by_norm: dict[str, dict] = {}
    for path in sorted((REPO / "semantic" / "songs").glob("*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        title = str(doc.get("title") or "")
        by_norm[_norm_title(title)] = {"path": path, "doc": doc}
    return by_norm


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch live official Suno playlist API (optional; not used in CI)",
    )
    args = parser.parse_args()

    snapshot = _load_snapshot(args.fixture, fetch=args.fetch)
    clips = _iter_clips(snapshot)
    songs = _load_songs()

    print(f"source: {snapshot.get('source') or args.fixture or DEFAULT_FIXTURE}")
    print(f"playlist clips: {len(clips)}")
    print(f"semantic songs: {len(songs)}")
    print()

    matched: set[str] = set()
    issues = 0
    for clip in clips:
        key = _norm_title(clip["title"])
        song = songs.get(key)
        if not song:
            print(f"UNMATCHED CLIP #{clip['position']}: {clip['title']} ({clip['id']})")
            issues += 1
            continue
        matched.add(key)
        doc = song["doc"]
        slug = doc["slug"]
        recordings = doc.get("recordings") or []
        ids = {str(r.get("externalId")) for r in recordings if isinstance(r, dict)}
        primary = next((r for r in recordings if isinstance(r, dict) and r.get("primary")), None)
        primary_id = str((primary or {}).get("externalId") or "")
        if clip["id"] not in ids:
            print(f"NEW RECORDING for {slug}: clip {clip['id']} not in YAML recordings")
            issues += 1
        elif clip["id"] != primary_id:
            print(f"PRIMARY DIFFERS for {slug}: playlist={clip['id']} yaml_primary={primary_id}")
            issues += 1
        else:
            print(f"OK #{clip['position']:02d} {slug} ← {clip['id']}")

    for key, song in songs.items():
        if key not in matched:
            print(f"SONG WITHOUT PLAYLIST CLIP: {song['doc'].get('slug')}")
            issues += 1

    print()
    print(f"issues: {issues}")
    print("Note: this tool never overwrites lyrics or authored prompts.")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
