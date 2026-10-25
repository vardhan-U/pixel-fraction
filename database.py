import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import DATA_DIR

logger = logging.getLogger(__name__)
STATE_FILE = DATA_DIR / "game_state.json"

class Database:
    def __init__(self, state_file: Path | None = None):
        self.state_file = state_file or STATE_FILE
        self.state = {
            "users": {},        # user_id: { "name": str, "score": int, "streak": int, "last_date": str }
            "chat_scores": {},  # chat_id: { user_id: int }
            "submissions": {},  # msg_id: { "user_id": str, "votes": { voter_id: vote_type } }
        }
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state file: {e}")

    def _save(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save state file: {e}")

    def record_submission(self, chat_id: int, user_id: int, user_name: str, points: int) -> dict:
        uid = str(user_id)
        cid = str(chat_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        user_data = self.state["users"].get(uid, {
            "name": user_name,
            "score": 0,
            "streak": 0,
            "last_date": "",
        })

        # Update display name
        user_data["name"] = user_name

        # Calculate streak
        last_date = user_data.get("last_date", "")
        if last_date == today:
            # Already submitted today; maintain streak
            pass
        elif last_date == yesterday:
            # Consecutive day
            user_data["streak"] += 1
            user_data["last_date"] = today
        else:
            # Missed or brand new
            user_data["streak"] = 1
            user_data["last_date"] = today

        # Add points
        user_data["score"] += points
        self.state["users"][uid] = user_data

        # Update chat-specific score
        if cid not in self.state["chat_scores"]:
            self.state["chat_scores"][cid] = {}
        self.state["chat_scores"][cid][uid] = self.state["chat_scores"][cid].get(uid, 0) + points

        self._save()
        return user_data

    def register_photo_submission(self, submission_id: str, author_id: int):
        self.state["submissions"][submission_id] = {
            "author_id": str(author_id),
            "votes": {},
        }
        self._save()

    def add_vote(self, submission_id: str, voter_id: int, vote_type: str) -> tuple[bool, str, dict]:
        """
        Records a vote.
        Returns (success: bool, message: str, vote_counts: dict)
        """
        sub = self.state["submissions"].get(submission_id)
        if not sub:
            return False, "Submission not found or expired.", {}

        vid = str(voter_id)
        if sub["author_id"] == vid:
            return False, "You cannot vote on your own photo! 😄", {}

        existing_vote = sub["votes"].get(vid)
        if existing_vote == vote_type:
            # Unvote
            del sub["votes"][vid]
            msg = "Vote removed."
        else:
            sub["votes"][vid] = vote_type
            msg = f"Voted {vote_type}!"

        # Calculate counts
        counts = {}
        for v in sub["votes"].values():
            counts[v] = counts.get(v, 0) + 1

        self._save()
        return True, msg, counts

    def get_leaderboard(self, chat_id: int, limit: int = 10) -> list[dict]:
        cid = str(chat_id)
        chat_users = self.state["chat_scores"].get(cid, {})

        leaderboard = []
        for uid, chat_score in chat_users.items():
            user_info = self.state["users"].get(uid, {})
            leaderboard.append({
                "user_id": uid,
                "name": user_info.get("name", f"Player {uid}"),
                "score": chat_score,
                "streak": user_info.get("streak", 0),
            })

        # Sort descending by score
        leaderboard.sort(key=lambda x: (x["score"], x["streak"]), reverse=True)
        return leaderboard[:limit]
