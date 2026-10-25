import json
import html
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

    def _cleanup_stale_daily_best(self, today: str):
        """Remove daily_best entries from past days so the file doesn't grow forever."""
        daily_best = self.state.get("daily_best", {})
        stale_keys = [k for k in daily_best if not k.endswith(f":{today}")]
        for k in stale_keys:
            del daily_best[k]

    def record_submission(self, chat_id: int, user_id: int, user_name: str, points: int) -> dict:
        """
        Records a photo submission with anti-farming protection.

        Each player can earn points for only ONE scored photo per chat per day.
        If a second qualifying photo scores higher, only the difference is credited.
        If it scores equal or lower, nothing is awarded.

        Returns a dict with:
          - All user_data fields (name, score, streak, last_date, first_played)
          - 'awarded': int — actual points credited this call (0 if duplicate/lower)
          - 'already_scored_today': int — the previous best score today in this chat (0 if first)
        """
        uid = str(user_id)
        cid = str(chat_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        now_iso = datetime.now(timezone.utc).isoformat()
        clean_name = user_name.strip() if user_name and user_name.strip() else "Player"
        user_data = self.state["users"].get(uid, {
            "name": clean_name,
            "score": 0,
            "streak": 0,
            "last_date": "",
            "first_played": now_iso,
        })

        # Update display name and ensure first_played is recorded
        user_data["name"] = clean_name
        if "first_played" not in user_data:
            user_data["first_played"] = now_iso

        # Calculate streak (once per calendar day, regardless of anti-farming)
        last_date = user_data.get("last_date", "")
        if last_date == today:
            pass
        elif last_date == yesterday:
            user_data["streak"] += 1
            user_data["last_date"] = today
        else:
            user_data["streak"] = 1
            user_data["last_date"] = today

        # --- Anti-farming: one best score per player per chat per day ---
        if "daily_best" not in self.state:
            self.state["daily_best"] = {}
        self._cleanup_stale_daily_best(today)

        daily_key = f"{cid}:{uid}:{today}"
        previous_best = self.state["daily_best"].get(daily_key, 0)

        if points > previous_best:
            awarded = points - previous_best
            self.state["daily_best"][daily_key] = points
        else:
            awarded = 0

        # Credit only the difference (never negative)
        user_data["score"] += awarded
        self.state["users"][uid] = user_data

        if cid not in self.state["chat_scores"]:
            self.state["chat_scores"][cid] = {}
        self.state["chat_scores"][cid][uid] = self.state["chat_scores"][cid].get(uid, 0) + awarded

        self._save()

        result = dict(user_data)
        result["awarded"] = awarded
        result["already_scored_today"] = previous_best
        return result

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

    def get_global_leaderboard(self) -> list[dict]:
        """
        Ranks all players across all chats by their total points summed over every chat, descending.
        Tie-breaker: current streak descending, then earlier first-played time, then user_id.
        Only players with total score > 0 are ranked.
        """
        players = []
        for uid, udata in self.state.get("users", {}).items():
            # Sum score over all chats
            chat_sum = sum(
                chat.get(str(uid), 0)
                for chat in self.state.get("chat_scores", {}).values()
            )
            total_score = max(chat_sum, udata.get("score", 0))
            if total_score <= 0:
                continue

            name = udata.get("name")
            display_name = name.strip() if (name and str(name).strip()) else "Player"

            players.append({
                "user_id": str(uid),
                "name": display_name,
                "score": total_score,
                "streak": udata.get("streak", 0),
                "first_played": udata.get("first_played") or "9999-12-31T23:59:59",
            })

        # Sort: score desc, streak desc, first_played asc, user_id asc
        players.sort(
            key=lambda u: (
                -u["score"],
                -u["streak"],
                u["first_played"],
                u["user_id"],
            )
        )
        return players


def format_globalboard_text(db: Database, caller_user_id: int | str | None = None) -> str:
    """
    Formats the global leaderboard into HTML-safe message text according to specification:
    - Top 15 with medals for top 3, numbers for rest.
    - If caller is in top 15, marks row with ' ← you' and adds no extra line.
    - If caller is not in top 15, adds a blank line and '#<rank> You: <score> pts (🔥 <streak> day streak)'.
    - If caller has no points yet, adds 'You haven't scored yet. Send /quest to start!'.
    - If nobody has scored, replies 'No scores yet. Be the first!'.
    """
    players = db.get_global_leaderboard()
    if not players:
        return "No scores yet. Be the first!"

    caller_id_str = str(caller_user_id) if caller_user_id is not None else None

    # Determine caller's rank if they exist in sorted players
    caller_rank = None
    caller_entry = None
    for idx, p in enumerate(players):
        if caller_id_str and p["user_id"] == caller_id_str:
            caller_rank = idx + 1
            caller_entry = p
            break

    top_15 = players[:15]
    lines = ["🌍 <b>GLOBAL PIXEL FRACTION LEADERBOARD</b> 🌍\n"]

    for idx, entry in enumerate(top_15):
        rank = idx + 1
        if rank == 1:
            prefix = "🥇"
        elif rank == 2:
            prefix = "🥈"
        elif rank == 3:
            prefix = "🥉"
        else:
            prefix = f"{rank}."

        safe_name = html.escape(entry["name"]) if entry["name"] else "Player"
        is_caller = (caller_id_str and entry["user_id"] == caller_id_str)
        you_marker = " ← you" if is_caller else ""
        lines.append(
            f"{prefix} <b>{safe_name}</b> — {entry['score']} pts (🔥 {entry['streak']} day streak){you_marker}"
        )

    # Caller footer handling
    if caller_id_str:
        if caller_rank is not None:
            # Caller is scored
            if caller_rank > 15:
                lines.append("")
                lines.append(
                    f"#{caller_rank} You: {caller_entry['score']} pts (🔥 {caller_entry['streak']} day streak)"
                )
        else:
            # Caller has not scored yet
            lines.append("")
            lines.append("You haven't scored yet. Send /quest to start!")

    return "\n".join(lines)
