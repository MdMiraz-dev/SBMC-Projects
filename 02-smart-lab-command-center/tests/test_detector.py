"""Module: tests/test_detector.py
Description: Unit and heuristic verification tests for DistractionDetector.
Adheres to AGENTS.md: Negative testing, false positive prevention, edge case handling.
"""

import pytest
from server.detector import DistractionDetector
from server.schemas import DistractionCategory


@pytest.fixture
def detector() -> DistractionDetector:
    return DistractionDetector()


@pytest.mark.parametrize(
    "title,process,expected_category",
    [
        ("YouTube Shorts - Viral Comedy Clip", "chrome.exe", DistractionCategory.REELS_SHORTS),
        ("Facebook Reels - Watch Trending Videos", "msedge.exe", DistractionCategory.REELS_SHORTS),
        ("Watch TikTok Videos Online", "chrome.exe", DistractionCategory.REELS_SHORTS),
        ("Playing Roblox - Mega Tower Obby", "RobloxPlayerBeta.exe", DistractionCategory.GAMING),
        ("Steam Community :: Market", "steam.exe", DistractionCategory.GAMING),
        ("Minecraft 1.20 - Survival World", "javaw.exe", DistractionCategory.GAMING),
        ("Home / X (formerly Twitter)", "firefox.exe", DistractionCategory.SOCIAL_MEDIA),
        ("Instagram Feed", "chrome.exe", DistractionCategory.SOCIAL_MEDIA),
        ("Netflix - Watch TV Shows Online", "msedge.exe", DistractionCategory.STREAMING),
    ],
)
def test_distraction_detection_positive(detector: DistractionDetector, title: str, process: str, expected_category: DistractionCategory):
    """Asserts that non-educational distracting applications and short-form videos are accurately flagged."""
    report = detector.evaluate(active_window_title=title, active_process_name=process)
    assert report.is_distracted is True
    assert report.category == expected_category
    assert report.matched_keyword is not None


@pytest.mark.parametrize(
    "title,process",
    [
        ("Python Full Course for Beginners - YouTube", "chrome.exe"),
        ("FastAPI Web Development Tutorial - YouTube", "firefox.exe"),
        ("As-Sunnah Foundation Islamic Research Lecture", "msedge.exe"),
        ("Visual Studio Code - main.py", "Code.exe"),
        ("PyCharm - Lead Automation Engine", "pycharm64.exe"),
        ("FastAPI Documentation - Endpoints", "chrome.exe"),
        ("Quran Translation & Tafseer - Word by Word", "chrome.exe"),
    ],
)
def test_educational_whitelist_false_positive_prevention(detector: DistractionDetector, title: str, process: str):
    """Asserts that legitimate educational and instructional videos are NOT falsely flagged."""
    report = detector.evaluate(active_window_title=title, active_process_name=process)
    assert report.is_distracted is False
    assert report.category == DistractionCategory.ALLOWED


def test_empty_window_handling(detector: DistractionDetector):
    """Asserts that empty or None titles do not trigger crashes or false alerts."""
    report_none = detector.evaluate(active_window_title="", active_process_name="")
    assert report_none.is_distracted is False
    assert report_none.category == DistractionCategory.ALLOWED

    report_spaces = detector.evaluate(active_window_title="   ", active_process_name="  ")
    assert report_spaces.is_distracted is False
