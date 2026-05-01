from __future__ import annotations

import unittest

from tubesiphon.ingest import parser


class VttParserTest(unittest.TestCase):
    def test_parse_vtt_returns_clean_unique_transcript_cues(self) -> None:
        vtt_text = """WEBVTT
Kind: captions
Language: en

NOTE captured for -b9Jvb3Fyqc

00:00:00.000 --> 00:00:02.000 align:start position:0%
<c>Trump May Crash the Market</c>

00:00:00.000 --> 00:00:02.000 align:start position:0%
<c>Trump May Crash the Market</c>

1
00:00:02.500 --> 00:00:04.000
<00:00:02.800>Get Cash Ready

STYLE
::cue { color: lime }

00:00:04.000 --> 00:00:05.500
War Panic AGAIN?
"""

        cues = parser.parse_vtt(vtt_text)

        self.assertEqual(
            cues,
            [
                parser.TranscriptCue(
                    start_time=0.0,
                    text="Trump May Crash the Market",
                ),
                parser.TranscriptCue(
                    start_time=2.5,
                    text="Get Cash Ready",
                ),
                parser.TranscriptCue(
                    start_time=4.0,
                    text="War Panic AGAIN?",
                ),
            ],
        )

    def test_parse_vtt_rejects_files_without_cues(self) -> None:
        with self.assertRaisesRegex(parser.VttParseError, "No transcript cues"):
            parser.parse_vtt("WEBVTT\n\nNOTE no subtitle cues\n")
