import io
import unittest
from PIL import Image

from color_engine import (
    analyze_pixel_fraction,
    compute_dhash,
    compute_similarity,
    COLOR_DEFINITIONS,
)
from database import Database, format_globalboard_text
from quest_manager import QuestManager, FALLBACK_QUESTS


def create_solid_image(rgb: tuple[int, int, int], size=(100, 100)) -> bytes:
    img = Image.new("RGB", size, color=rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def create_split_image(rgb1: tuple[int, int, int], rgb2: tuple[int, int, int], size=(100, 100)) -> bytes:
    img = Image.new("RGB", size)
    half = size[0] // 2
    for x in range(size[0]):
        for y in range(size[1]):
            img.putpixel((x, y), rgb1 if x < half else rgb2)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestPixelFractionEngine(unittest.TestCase):

    def test_solid_red_detection(self):
        # Pure red
        img_bytes = create_solid_image((255, 0, 0))
        result = analyze_pixel_fraction(img_bytes, "red")
        self.assertGreaterEqual(result["percentage"], 95.0)

        # Checking green on red image should be 0%
        result_green = analyze_pixel_fraction(img_bytes, "green")
        self.assertEqual(result_green["percentage"], 0.0)

    def test_solid_green_detection(self):
        # Pure green
        img_bytes = create_solid_image((0, 200, 0))
        result = analyze_pixel_fraction(img_bytes, "green")
        self.assertGreaterEqual(result["percentage"], 95.0)

    def test_split_image_percentages(self):
        # 50% Red, 50% Blue
        img_bytes = create_split_image((255, 0, 0), (0, 0, 255))
        result_red = analyze_pixel_fraction(img_bytes, "red")
        result_blue = analyze_pixel_fraction(img_bytes, "blue")

        self.assertTrue(45.0 <= result_red["percentage"] <= 55.0)
        self.assertTrue(45.0 <= result_blue["percentage"] <= 55.0)

    def test_anticheat_identical_images(self):
        img_bytes = create_split_image((255, 100, 0), (0, 150, 200))
        hash1 = compute_dhash(img_bytes)
        hash2 = compute_dhash(img_bytes)

        similarity = compute_similarity(hash1, hash2)
        self.assertEqual(similarity, 1.0)

    def test_anticheat_different_images(self):
        # Image 1: Left-to-right gradient (p1 < p2)
        img1 = Image.new("L", (100, 100))
        for x in range(100):
            for y in range(100):
                img1.putpixel((x, y), int(x * 2.5))
        buf1 = io.BytesIO()
        img1.convert("RGB").save(buf1, format="JPEG")

        # Image 2: Right-to-left gradient (p1 > p2)
        img2 = Image.new("L", (100, 100))
        for x in range(100):
            for y in range(100):
                img2.putpixel((x, y), int((99 - x) * 2.5))
        buf2 = io.BytesIO()
        img2.convert("RGB").save(buf2, format="JPEG")

        hash1 = compute_dhash(buf1.getvalue())
        hash2 = compute_dhash(buf2.getvalue())
        similarity = compute_similarity(hash1, hash2)
        self.assertLess(similarity, 0.20)

    def test_database_and_voting(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            test_state_file = Path(tmpdir) / "test_state.json"
            db = Database(state_file=test_state_file)
            chat_id = 99999
            author_id = 1001
            voter_id = 2002

            # 1. Author records submission
            user = db.record_submission(chat_id, author_id, "Alice", 10)
            self.assertEqual(user["score"], 10)
            self.assertEqual(user["streak"], 1)

            # 2. Register photo submission
            sub_id = f"{chat_id}_123"
            db.register_photo_submission(sub_id, author_id)

            # 3. Author tries to vote on own photo (Should fail)
            success, msg, _ = db.add_vote(sub_id, author_id, "creative")
            self.assertFalse(success)

            # 4. Peer votes
            success, msg, counts = db.add_vote(sub_id, voter_id, "creative")
            self.assertTrue(success)
            self.assertEqual(counts.get("creative"), 1)

            # 5. Check leaderboard
            lb = db.get_leaderboard(chat_id)
            self.assertTrue(len(lb) > 0)
            self.assertEqual(lb[0]["name"], "Alice")

    def test_fallback_quest_generation(self):
        mgr = QuestManager()
        # Temporarily mock empty unsplash key
        quest = mgr.fetch_new_quest()
        self.assertIn("color_key", quest)
        self.assertIn("photo_url", quest)
        self.assertIn("photographer", quest)
        self.assertIn("emoji", quest)

    def test_admin_handling(self):
        import bot
        from unittest.mock import patch

        # Case 1: ADMIN_ID is set
        with patch.object(bot, "ADMIN_ID", "12345"):
            self.assertTrue(bot.is_admin(12345))
            self.assertTrue(bot.is_admin("12345"))
            self.assertFalse(bot.is_admin(99999))
            self.assertFalse(bot.is_admin("99999"))

        # Case 2: ADMIN_ID is empty/missing -> treat as no admin
        with patch.object(bot, "ADMIN_ID", ""):
            self.assertFalse(bot.is_admin(12345))
            self.assertFalse(bot.is_admin(0))
            self.assertFalse(bot.is_admin(None))

    def test_logger_levels(self):
        import logging
        import bot  # imports and configures loggers
        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)
        self.assertGreaterEqual(logging.getLogger("httpcore").level, logging.WARNING)

    def test_globalboard_empty_database(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "empty.json")
            text = format_globalboard_text(db, caller_user_id=123)
            self.assertEqual(text, "No scores yet. Be the first!")

    def test_globalboard_fewer_than_15_players(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            # 5 players
            for i in range(1, 6):
                db.record_submission(100, i, f"Player{i}", i * 10)
            
            # Caller is Player 4 (score 40, rank 2)
            text = format_globalboard_text(db, caller_user_id=4)
            lines = text.strip().split("\n")
            self.assertTrue(lines[0].startswith("🌍 <b>GLOBAL PIXEL FRACTION LEADERBOARD</b> 🌍"))
            self.assertIn("🥇 <b>Player5</b> — 50 pts", text)
            self.assertIn("🥈 <b>Player4</b> — 40 pts (🔥 1 day streak) ← you", text)
            self.assertIn("🥉 <b>Player3</b> — 30 pts", text)
            self.assertIn("4. <b>Player2</b> — 20 pts", text)
            self.assertIn("5. <b>Player1</b> — 10 pts", text)
            # Since caller is in top 15, no extra rank footer line added
            self.assertNotIn("#2 You:", text)

    def test_globalboard_exactly_15_players(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            for i in range(1, 16):
                db.record_submission(100, i, f"Player{i}", i * 10)
            
            # Caller is rank 15 (Player 1, score 10)
            text = format_globalboard_text(db, caller_user_id=1)
            lines = text.strip().split("\n")
            # 1 title line, 1 empty line from \n, 15 player lines = 17 lines total
            player_lines = [l for l in lines if l and not l.startswith("🌍")]
            self.assertEqual(len(player_lines), 15)
            self.assertIn("15. <b>Player1</b> — 10 pts (🔥 1 day streak) ← you", text)
            self.assertNotIn("#15 You:", text)

    def test_globalboard_more_than_15_caller_outside_top_15(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            # 20 players (scores 200 down to 10)
            for i in range(1, 21):
                db.record_submission(100, i, f"Player{i}", i * 10)
            
            # Caller is Player 2 (score 20, rank 19 out of 20)
            text = format_globalboard_text(db, caller_user_id=2)
            # Only top 15 displayed in main list
            self.assertIn("🥇 <b>Player20</b> — 200 pts", text)
            self.assertIn("15. <b>Player6</b> — 60 pts", text)
            self.assertNotIn("16.", text)
            # Footer contains caller line
            self.assertIn("#19 You: 20 pts (🔥 1 day streak)", text)

    def test_globalboard_ties_and_stability(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            # Setup two players with equal scores and equal streaks
            db.state["users"]["101"] = {
                "name": "EarlierAlice",
                "score": 50,
                "streak": 2,
                "first_played": "2026-10-25T10:00:00",
            }
            db.state["users"]["102"] = {
                "name": "LaterBob",
                "score": 50,
                "streak": 2,
                "first_played": "2026-10-25T12:00:00",
            }
            text = format_globalboard_text(db, caller_user_id=None)
            lines = [l for l in text.split("\n") if l and not l.startswith("🌍")]
            self.assertIn("EarlierAlice", lines[0])
            self.assertIn("LaterBob", lines[1])

    def test_globalboard_caller_zero_points(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            db.record_submission(100, 999, "Scorer", 25)
            # Caller has not scored (ID 12345 has 0 points)
            text = format_globalboard_text(db, caller_user_id=12345)
            self.assertIn("🥇 <b>Scorer</b> — 25 pts", text)
            self.assertIn("You haven't scored yet. Send /quest to start!", text)

    def test_globalboard_privacy_and_empty_name(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Database(state_file=Path(tmpdir) / "test.json")
            # HTML special characters in name and empty name
            db.state["users"]["101"] = {
                "name": "<Admin&Hacker>",
                "score": 50,
                "streak": 1,
                "first_played": "2026-10-25T10:00:00",
            }
            db.state["users"]["102"] = {
                "name": "   ",
                "score": 25,
                "streak": 1,
                "first_played": "2026-10-25T10:05:00",
            }
            text = format_globalboard_text(db, caller_user_id=None)
            self.assertIn("&lt;Admin&amp;Hacker&gt;", text)
            self.assertNotIn("<Admin&Hacker>", text)
            self.assertIn("<b>Player</b>", text)
            self.assertNotIn("101", text)
            self.assertNotIn("102", text)


if __name__ == "__main__":
    unittest.main()
