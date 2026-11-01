import stat

from roborock.data import UserData

from roborock_controller.credentials import Credentials

USER_DATA = {
    "uid": 1,
    "token": "token",
    "rriot": {
        "u": "u",
        "s": "s",
        "h": "h",
        "k": "k",
        "r": {"r": "EU", "a": "https://api", "m": "ssl://mqtt", "l": "https://wood"},
    },
}


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "config" / "secrets.json"
    Credentials("me@example.com", UserData.from_dict(USER_DATA), "https://euiot.roborock.com").save(path)

    loaded = Credentials.load(path)

    assert loaded.username == "me@example.com"
    assert loaded.base_url == "https://euiot.roborock.com"
    assert loaded.user_data.rriot.r.a == "https://api"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
