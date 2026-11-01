import json
import os
from dataclasses import dataclass
from pathlib import Path

from roborock.data import UserData
from roborock.devices.device_manager import UserParams


@dataclass
class Credentials:
    username: str
    user_data: UserData
    base_url: str

    def user_params(self) -> UserParams:
        return UserParams(username=self.username, user_data=self.user_data, base_url=self.base_url)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = {"username": self.username, "base_url": self.base_url, "user_data": self.user_data.as_dict()}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(content, file, indent=2)

    @classmethod
    def load(cls, path: Path) -> "Credentials":
        content = json.loads(path.read_text())
        return cls(content["username"], UserData.from_dict(content["user_data"]), content["base_url"])
