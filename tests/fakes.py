from types import SimpleNamespace

from roborock.data import (
    HomeDataScene,
    RoborockDockErrorCode,
    RoborockErrorCode,
    RoborockInCleaning,
    RoborockStateCode,
)
from roborock.exceptions import RoborockException


class FakeStatus:
    def __init__(self) -> None:
        self.fail = False
        self.state = RoborockStateCode.charging
        self.battery = 98
        self.error_code = RoborockErrorCode.none
        self.dock_error_status = RoborockDockErrorCode.ok
        self.square_meter_clean_area = 12.5
        self.clean_time = 900
        self.clean_percent = None
        self.in_cleaning = RoborockInCleaning.complete
        self.in_returning = 0

    @property
    def state_name(self) -> str:
        return self.state.name

    async def refresh(self) -> None:
        if self.fail:
            raise RoborockException("timeout")


class FakeRoutines:
    def __init__(self) -> None:
        self.fetched = 0
        self.executed: list[int] = []

    async def get_routines(self) -> list[HomeDataScene]:
        self.fetched += 1
        return [HomeDataScene(4146859, "Full Cleaning"), HomeDataScene(4207676, "Wohnzimmer")]

    async def execute_routine(self, routine_id: int) -> None:
        self.executed.append(routine_id)


class FakeCommand:
    def __init__(self) -> None:
        self.fail = False
        self.sent: list[str] = []

    async def send(self, command, params=None) -> None:
        if self.fail:
            raise RoborockException("device busy")
        self.sent.append(command.value)


class FakeDevice:
    def __init__(self) -> None:
        self.name = "robocop"
        self.is_local_connected = True
        self.v1_properties = SimpleNamespace(status=FakeStatus(), routines=FakeRoutines(), command=FakeCommand())


class FakeClock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now
