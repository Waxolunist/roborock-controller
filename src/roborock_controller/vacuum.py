import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from roborock import RoborockCommand
from roborock.exceptions import RoborockException

from roborock_controller.metrics import Metrics

logger = logging.getLogger(__name__)

ROUTINES_MAX_AGE = 300


class UnknownRoutine(Exception):
    pass


@dataclass
class Routine:
    id: int
    name: str


@dataclass
class StartedRoutine:
    routine: Routine
    started_at: float


class Vacuum:
    def __init__(self, metrics: Metrics, clock=time.time) -> None:
        self.metrics = metrics
        self.clock = clock
        self.device = None
        self.reachable = False
        self.last_refresh: float | None = None
        self.last_routine: StartedRoutine | None = None
        self._routines: list[Routine] = []
        self._routines_fetched_at: float | None = None

    @property
    def connected(self) -> bool:
        return self.device is not None

    def attach(self, device) -> None:
        self.device = device

    def cloud_rejected(self) -> None:
        logger.error("The Roborock cloud rejected the credentials, a new login is needed")
        self.metrics.cloud_auth_ok.set(0)

    async def refresh(self) -> bool:
        if self.device is None:
            self._unreachable()
            return False
        status = self.device.v1_properties.status
        try:
            await status.refresh()
        except RoborockException as e:
            logger.warning("Status refresh failed: %s", e)
            self._unreachable()
            return False
        self.reachable = True
        self.last_refresh = self.clock()
        self.metrics.status(status, self.device.is_local_connected, self.last_refresh)
        return True

    def fresh(self, max_age: float) -> bool:
        return self.last_refresh is not None and self.clock() - self.last_refresh <= max_age

    def status(self) -> dict:
        local = bool(self.device and self.device.is_local_connected)
        result = {
            "reachable": self.reachable,
            "local_connection": local,
            "connection": ("local" if local else "cloud") if self.reachable else "unreachable",
            "last_update": _iso(self.last_refresh),
            "last_routine": None,
        }
        if self.last_routine is not None:
            result["last_routine"] = {
                "id": self.last_routine.routine.id,
                "name": self.last_routine.routine.name,
                "started_at": _iso(self.last_routine.started_at),
            }
        if self.device is not None and self.last_refresh is not None:
            status = self.device.v1_properties.status
            result |= {
                "name": self.device.name,
                "state": status.state_name,
                "battery": status.battery,
                "error": _name(status.error_code),
                "dock_error": _name(status.dock_error_status),
                "clean_area_m2": status.square_meter_clean_area,
                "clean_time_s": status.clean_time,
                "clean_percent": status.clean_percent,
            }
        return result

    async def routines(self) -> list[Routine]:
        if self._routines_fetched_at is not None and self.clock() - self._routines_fetched_at < ROUTINES_MAX_AGE:
            return self._routines
        scenes = await self._properties().routines.get_routines()
        self._routines = [Routine(scene.id, scene.name) for scene in scenes]
        self._routines_fetched_at = self.clock()
        return self._routines

    async def run_routine(self, routine_id: int) -> Routine:
        routine = next((r for r in await self.routines() if r.id == routine_id), None)
        if routine is None:
            raise UnknownRoutine(routine_id)
        await self._run("routine", lambda p: p.routines.execute_routine(routine.id))
        self.last_routine = StartedRoutine(routine, self.clock())
        return routine

    async def stop(self) -> None:
        await self._run("stop", lambda p: p.command.send(RoborockCommand.APP_STOP))

    async def dock(self) -> None:
        await self._run("dock", lambda p: p.command.send(RoborockCommand.APP_CHARGE))

    def _properties(self):
        if self.device is None:
            raise RoborockException("Not connected to the vacuum")
        return self.device.v1_properties

    def _unreachable(self) -> None:
        self.reachable = False
        self.metrics.unreachable()

    async def _run(self, command: str, call) -> None:
        try:
            await call(self._properties())
        except RoborockException:
            self.metrics.command(command, False)
            raise
        self.metrics.command(command, True)
        logger.info("Command %s sent", command)


def _name(value) -> str | None:
    return None if value is None else value.name


def _iso(timestamp: float | None) -> str | None:
    return None if timestamp is None else datetime.fromtimestamp(timestamp, UTC).isoformat()
