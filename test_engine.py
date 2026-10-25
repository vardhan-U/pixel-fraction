import io
import unittest
from PIL import Image

from color_engine import (
    analyze_pixel_fraction,
    compute_dhash,
    compute_similarity,
    COLOR_DEFINITIONS,
)
from database import Database
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


if __name__ == "__main__":
    unittest.main()
