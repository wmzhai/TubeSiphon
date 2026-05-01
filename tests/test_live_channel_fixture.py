from __future__ import annotations

import os
import unittest

from tubesiphon.ingest.channel import fetch_channel_metadata, parse_channel_metadata


LIVE_TEST_ENV_VAR = "TUBESIPHON_RUN_LIVE_TESTS"
LIVE_CHANNEL_URL = "https://www.youtube.com/@nicolasyounglive"
EXPECTED_CHANNEL_ID = "UCXUP_aBLQBNFgLjvnrMTHtw"
KNOWN_VIDEO_ID = "-b9Jvb3Fyqc"


@unittest.skipUnless(
    os.environ.get(LIVE_TEST_ENV_VAR) == "1",
    f"set {LIVE_TEST_ENV_VAR}=1 to run live YouTube fixture tests",
)
class LiveChannelFixtureTest(unittest.TestCase):
    def test_canonical_channel_fetches_real_video_list(self) -> None:
        payload = fetch_channel_metadata(LIVE_CHANNEL_URL)
        metadata = parse_channel_metadata(payload, source_url=LIVE_CHANNEL_URL)

        video_ids = {video.video_id for video in metadata.videos}

        self.assertEqual(metadata.channel_id, EXPECTED_CHANNEL_ID)
        self.assertIn(KNOWN_VIDEO_ID, video_ids)
        self.assertGreaterEqual(len(video_ids), 1)
        self.assertEqual(metadata.skipped_video_count, 0)
