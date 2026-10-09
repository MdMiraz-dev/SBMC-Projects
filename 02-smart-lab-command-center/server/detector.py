"""Module: server/detector.py
Description: Active window & process distraction heuristic detection engine.
Identifies Reels, YouTube Shorts, social media, and gaming during educational lab hours.
Adheres to AGENTS.md: Modular heuristics, clean domain boundaries, negative testable.
"""

import re
from typing import Dict, List, Optional, Pattern, Tuple
from .schemas import DistractionCategory, DistractionReport


class DistractionDetector:
    """Heuristic engine evaluating active window titles and process names against lab rules."""

    def __init__(self, custom_keywords: Optional[Dict[DistractionCategory, List[str]]] = None):
        # High-priority short-form video triggers (Facebook Reels, YouTube Shorts, TikTok)
        self.reels_shorts_patterns: List[Pattern[str]] = [
            re.compile(r"\bshorts\b", re.IGNORECASE),
            re.compile(r"youtube\s*shorts", re.IGNORECASE),
            re.compile(r"#shorts\b", re.IGNORECASE),
            re.compile(r"\breels\b", re.IGNORECASE),
            re.compile(r"facebook\s*reels", re.IGNORECASE),
            re.compile(r"instagram\s*reels", re.IGNORECASE),
            re.compile(r"\btiktok\b", re.IGNORECASE),
        ]

        # Social media distractions
        self.social_patterns: List[Pattern[str]] = [
            re.compile(r"\bfacebook\b", re.IGNORECASE),
            re.compile(r"\binstagram\b", re.IGNORECASE),
            re.compile(r"\btwitter\b|\bx\.com\b", re.IGNORECASE),
            re.compile(r"\breddit\b", re.IGNORECASE),
            re.compile(r"\bsnapchat\b", re.IGNORECASE),
        ]

        # Gaming & launcher patterns
        self.gaming_patterns: List[Pattern[str]] = [
            re.compile(r"\bsteam\b", re.IGNORECASE),
            re.compile(r"\broblox\b", re.IGNORECASE),
            re.compile(r"\bminecraft\b", re.IGNORECASE),
            re.compile(r"\bvalorant\b", re.IGNORECASE),
            re.compile(r"\bpubg\b", re.IGNORECASE),
            re.compile(r"\bfree\s*fire\b", re.IGNORECASE),
            re.compile(r"\bcounter[- ]strike\b|\bcs2\b", re.IGNORECASE),
            re.compile(r"\bgta\s*v?\b", re.IGNORECASE),
            re.compile(r"\bdiscord\b", re.IGNORECASE),
        ]

        # General non-educational streaming
        self.streaming_patterns: List[Pattern[str]] = [
            re.compile(r"\bnetflix\b", re.IGNORECASE),
            re.compile(r"\bprime\s*video\b", re.IGNORECASE),
            re.compile(r"\btwitch\b", re.IGNORECASE),
        ]

        # Educational exceptions (e.g. YouTube tutorial, As-Sunnah lecture, programming courses)
        self.educational_exceptions: List[Pattern[str]] = [
            re.compile(r"\btutorial\b", re.IGNORECASE),
            re.compile(r"\blecture\b", re.IGNORECASE),
            re.compile(r"\bcourse\b", re.IGNORECASE),
            re.compile(r"\bpython\b", re.IGNORECASE),
            re.compile(r"\bprogramming\b", re.IGNORECASE),
            re.compile(r"\bas-sunnah\b|\bassunnah\b", re.IGNORECASE),
            re.compile(r"\bquran\b|\bhadith\b", re.IGNORECASE),
            re.compile(r"\bvisual studio\b|\bvs\s*code\b|\bpycharm\b", re.IGNORECASE),
            re.compile(r"\bdocumentation\b|\bdocs\b", re.IGNORECASE),
        ]

        # Apply custom overrides if provided
        if custom_keywords:
            self._apply_custom_keywords(custom_keywords)

    def _apply_custom_keywords(self, custom: Dict[DistractionCategory, List[str]]) -> None:
        for cat, keywords in custom.items():
            compiled = [re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE) for k in keywords]
            if cat == DistractionCategory.REELS_SHORTS:
                self.reels_shorts_patterns.extend(compiled)
            elif cat == DistractionCategory.SOCIAL_MEDIA:
                self.social_patterns.extend(compiled)
            elif cat == DistractionCategory.GAMING:
                self.gaming_patterns.extend(compiled)
            elif cat == DistractionCategory.STREAMING:
                self.streaming_patterns.extend(compiled)

    def evaluate(self, active_window_title: str, active_process_name: str = "") -> DistractionReport:
        """
        Evaluates active foreground window title and process name.
        Returns a structured DistractionReport.
        """
        title = (active_window_title or "").strip()
        proc = (active_process_name or "").strip()
        combined_text = f"{title} {proc}".strip()

        if not combined_text:
            return DistractionReport(
                is_distracted=False,
                category=DistractionCategory.ALLOWED,
                flagged_title=title,
                message="No active foreground window title detected.",
            )

        # 1. Check for immediate Short-form video triggers (Highest Priority, even inside YouTube)
        for pattern in self.reels_shorts_patterns:
            match = pattern.search(combined_text)
            if match:
                return DistractionReport(
                    is_distracted=True,
                    category=DistractionCategory.REELS_SHORTS,
                    flagged_title=title,
                    matched_keyword=match.group(0),
                    severity="CRITICAL",
                    message=f"Short-form video detected ({match.group(0)}). Distraction alert dispatched.",
                )

        # 2. Check for Gaming triggers (Critical)
        for pattern in self.gaming_patterns:
            match = pattern.search(combined_text)
            if match:
                return DistractionReport(
                    is_distracted=True,
                    category=DistractionCategory.GAMING,
                    flagged_title=title,
                    matched_keyword=match.group(0),
                    severity="CRITICAL",
                    message=f"Gaming application detected ({match.group(0)}). Prohibited during lab hours.",
                )

        # 3. Check for Educational White-list Exception
        # If the window has general YouTube or web search, but clearly contains tutorial/course/Islamic material
        is_educational = any(p.search(combined_text) for p in self.educational_exceptions)
        if is_educational:
            return DistractionReport(
                is_distracted=False,
                category=DistractionCategory.ALLOWED,
                flagged_title=title,
                severity="INFO",
                message="Window matches verified educational or instructional content.",
            )

        # 4. Check for General Social Media (Warning)
        for pattern in self.social_patterns:
            match = pattern.search(combined_text)
            if match:
                return DistractionReport(
                    is_distracted=True,
                    category=DistractionCategory.SOCIAL_MEDIA,
                    flagged_title=title,
                    matched_keyword=match.group(0),
                    severity="WARNING",
                    message=f"Social media portal active ({match.group(0)}). Attention required.",
                )

        # 5. Check for General Streaming (Warning)
        for pattern in self.streaming_patterns:
            match = pattern.search(combined_text)
            if match:
                return DistractionReport(
                    is_distracted=True,
                    category=DistractionCategory.STREAMING,
                    flagged_title=title,
                    matched_keyword=match.group(0),
                    severity="WARNING",
                    message=f"Non-educational video streaming detected ({match.group(0)}).",
                )

        # Default: Allowed
        return DistractionReport(
            is_distracted=False,
            category=DistractionCategory.ALLOWED,
            flagged_title=title,
            severity="INFO",
            message="Active window compliant with lab policy.",
        )
