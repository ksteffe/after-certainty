"""Songs collection (schemaVersion 2.6) — compositions, recordings, playlists."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]


def test_song_yaml_count_and_primary_recording() -> None:
    songs_dir = REPO / "semantic" / "songs"
    paths = sorted(songs_dir.glob("*.yml"))
    assert len(paths) == 36
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert doc["slug"] == path.stem
        lyrics = REPO / doc["lyricsPath"]
        assert lyrics.is_file(), doc["lyricsPath"]
        primaries = [r for r in doc["recordings"] if r.get("primary") is True]
        assert len(primaries) == 1, path.name
        assert primaries[0]["platform"] == "suno"
        assert primaries[0]["externalId"]
        # Version suffixes must not leak into composition title
        assert "(" not in doc["title"]


def test_playlist_resolves_to_songs() -> None:
    playlist = yaml.safe_load(
        (REPO / "semantic" / "playlists" / "after-certainty.yml").read_text(encoding="utf-8")
    )
    assert playlist["slug"] == "after-certainty"
    assert len(playlist["tracks"]) == 36
    song_slugs = {p.stem for p in (REPO / "semantic" / "songs").glob("*.yml")}
    for track in playlist["tracks"]:
        assert track["songSlug"] in song_slugs
        assert track["recordingExternalId"]


def test_manifest_includes_songs_and_reverse_links(semantic_manifest: dict) -> None:
    assert semantic_manifest["schemaVersion"] == "2.6"
    songs = semantic_manifest.get("songs") or []
    playlists = semantic_manifest.get("playlists") or []
    assert len(songs) == 36
    assert len(playlists) == 1
    assert playlists[0]["slug"] == "after-certainty"
    by_slug = {s["slug"]: s for s in songs}
    assert "the-third-thing" in by_slug
    media = by_slug["the-third-thing"].get("relatedMedia") or []
    assert any(m.get("externalId") == "CvgNJ4RoUIc" for m in media)
    # Historical + primary for replaced clips
    grain = by_slug["the-grain-remains"]["recordings"]
    assert len(grain) == 2
    assert sum(1 for r in grain if r.get("primary")) == 1
    books_with_songs = [b for b in semantic_manifest["books"] if b.get("songs")]
    assert books_with_songs
    glossary_with = [g for g in semantic_manifest["glossary"] if g.get("relatedSongs")]
    assert glossary_with
