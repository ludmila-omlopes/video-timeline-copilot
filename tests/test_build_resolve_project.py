from __future__ import annotations

from pathlib import Path

import pytest

from helpers.build_resolve_project import create_timelines_from_edl


class FakeTimelineItem:
    def __init__(self) -> None:
        self.properties: dict = {}

    def SetProperty(self, properties: dict) -> None:
        self.properties.update(properties)


class FakeTimeline:
    def __init__(self, item: FakeTimelineItem) -> None:
        self.item = item
        self.markers: list[dict] = []

    def GetName(self) -> str:
        return "Main"

    def GetItemListInTrack(self, track_type: str, index: int) -> list[FakeTimelineItem]:
        assert track_type == "video"
        assert index == 1
        return [self.item]

    def AddMarker(self, *args) -> None:
        self.markers.append({"args": args})


class FakeMediaPool:
    def __init__(self, timeline: FakeTimeline) -> None:
        self.timeline = timeline

    def CreateTimelineFromClips(self, name: str, clip_infos: list[dict]) -> FakeTimeline:
        assert name == "Main"
        assert len(clip_infos) == 1
        return self.timeline

    def DeleteTimelines(self, timelines: list[FakeTimeline]) -> bool:
        return True


class FakeProject:
    def __init__(self, media_pool: FakeMediaPool) -> None:
        self.media_pool = media_pool
        self.settings: dict[str, str] = {}

    def GetTimelineCount(self) -> int:
        return 0

    def GetTimelineByIndex(self, index: int):
        return None

    def SetSetting(self, key: str, value: str) -> None:
        self.settings[key] = value

    def SetCurrentTimeline(self, timeline: FakeTimeline) -> None:
        self.timeline = timeline

    def GetMediaPool(self) -> FakeMediaPool:
        return self.media_pool


class FakeMediaStorage:
    def AddItemListToMediaPool(self, paths: list[str]) -> list[object]:
        assert len(paths) == 1
        return [object()]


class FakeResolve:
    def __init__(self) -> None:
        self.media_storage = FakeMediaStorage()

    def GetMediaStorage(self) -> FakeMediaStorage:
        return self.media_storage


def test_create_timelines_compensates_resolve_zoom_for_transform_position(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"")
    item = FakeTimelineItem()
    timeline = FakeTimeline(item)
    project = FakeProject(FakeMediaPool(timeline))
    edl = {
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {
                        "source": "A001",
                        "source_start": 0.0,
                        "source_end": 1.0,
                        "record_start": 0.0,
                        "transform": {"zoom": 1.07, "pan": 0.0, "tilt": -151.2},
                    }
                ],
            }
        ],
    }

    create_timelines_from_edl(project, FakeResolve(), edl, tmp_path)

    assert item.properties == {"ZoomX": 1.28, "ZoomY": 1.28, "Pan": 0.0, "Tilt": -151.2}


def test_create_timelines_rejects_record_gap_before_resolve_import(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"")
    edl = {
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [
                    {"source": "A001", "source_start": 0.0, "source_end": 1.0, "record_start": 0.0},
                    {"source": "A001", "source_start": 3.0, "source_end": 4.0, "record_start": 2.0},
                ],
            }
        ],
    }

    with pytest.raises(RuntimeError, match="record gaps"):
        create_timelines_from_edl(FakeProject(FakeMediaPool(FakeTimeline(FakeTimelineItem()))), FakeResolve(), edl, tmp_path)


def test_create_timelines_rejects_half_second_clip_before_resolve_import(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"")
    edl = {
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [{"source": "A001", "source_start": 0.0, "source_end": 0.5, "record_start": 0.0}],
            }
        ],
    }

    with pytest.raises(RuntimeError, match="shorter than"):
        create_timelines_from_edl(FakeProject(FakeMediaPool(FakeTimeline(FakeTimelineItem()))), FakeResolve(), edl, tmp_path)


def test_create_timelines_rejects_retimed_ranges_before_resolve_import(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"")
    edl = {
        "fps": 30,
        "timelines": [
            {
                "name": "Main",
                "resolution": [1920, 1080],
                "sources": {"A001": "raw/clip.mp4"},
                "ranges": [{"source": "A001", "source_start": 0.0, "source_end": 4.0, "record_start": 0.0, "speed": 2.0}],
            }
        ],
    }

    with pytest.raises(RuntimeError, match="does not support retimed ranges"):
        create_timelines_from_edl(FakeProject(FakeMediaPool(FakeTimeline(FakeTimelineItem()))), FakeResolve(), edl, tmp_path)
