from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta


@dataclass
class UserData:
    """Data class representing user information."""
    message_thread_id: int | None
    message_silent_id: int | None
    message_silent_mode: bool

    id: int
    full_name: str
    username: str | None
    state: str = "member"
    is_banned: bool = False
    language_code: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.id or self.id <= 0:
            raise ValueError(f"UserData.id must be positive, got: {self.id}")
        if not self.full_name or not self.full_name.strip():
            self.full_name = "Unknown"
        if not self.created_at:
            self.created_at = datetime.now(
                timezone(timedelta(hours=3))
            ).strftime("%Y-%m-%d %H:%M:%S %Z")

    def to_dict(self) -> dict:
        """
        Converts UserData object to a dictionary.

        :return: Dictionary representation of UserData.
        """
        return asdict(self)
