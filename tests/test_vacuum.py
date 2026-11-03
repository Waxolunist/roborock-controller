import pytest
from roborock.data import RoborockDockErrorCode, RoborockErrorCode, RoborockInCleaning, RoborockStateCode
from roborock.exceptions import RoborockException

from roborock_controller.metrics import COMMANDS, Metrics
from roborock_controller.vacuum import NotPossible, UnknownRoutine, Vacuum
from tests.fakes import FakeClock, FakeDevice


def sample(metrics: Metrics, name: str, labels: dict | None = None) -> float | None:
    return metrics.registry.get_sample_value(name, labels or {})


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def device():
    return FakeDevice()


@pytest.fixture
def vacuum(device, clock):
    vacuum = Vacuum(Metrics(), clock, settle_seconds=0)
    vacuum.attach(device)
    return vacuum


async def test_refresh_records_the_status(vacuum, device):
    device.v1_properties.status.error_code = RoborockErrorCode.main_brush_jammed
    device.v1_properties.status.dock_error_status = RoborockDockErrorCode.water_empty

    assert await vacuum.refresh()

    metrics = vacuum.metrics
    assert sample(metrics, "roborock_up") == 1
    assert sample(metrics, "roborock_local_connection") == 1
    assert sample(metrics, "roborock_battery_percent") == 98
    assert sample(metrics, "roborock_state", {"state": "charging"}) == 1
    assert sample(metrics, "roborock_error_code") == RoborockErrorCode.main_brush_jammed.value
    assert sample(metrics, "roborock_error", {"error": "main_brush_jammed"}) == 1
    assert sample(metrics, "roborock_dock_error_code") == RoborockDockErrorCode.water_empty.value
    assert sample(metrics, "roborock_dock_error", {"error": "water_empty"}) == 1


async def test_a_new_state_replaces_the_old_one(vacuum, device):
    await vacuum.refresh()
    device.v1_properties.status.state = RoborockStateCode.cleaning

    await vacuum.refresh()

    assert sample(vacuum.metrics, "roborock_state", {"state": "charging"}) is None
    assert sample(vacuum.metrics, "roborock_state", {"state": "cleaning"}) == 1


async def test_a_failed_refresh_marks_the_vacuum_unreachable(vacuum, device):
    await vacuum.refresh()
    device.v1_properties.status.fail = True

    assert not await vacuum.refresh()

    assert sample(vacuum.metrics, "roborock_up") == 0
    assert vacuum.status()["reachable"] is False


async def test_refresh_without_a_device_is_unreachable(clock):
    vacuum = Vacuum(Metrics(), clock)

    assert not await vacuum.refresh()

    assert sample(vacuum.metrics, "roborock_up") == 0
    assert vacuum.status() == {
        "reachable": False,
        "local_connection": False,
        "connection": "unreachable",
        "last_update": None,
        "last_routine": None,
        "can_pause": False,
        "can_resume": False,
    }


async def test_fresh_follows_the_last_refresh(vacuum, clock):
    assert not vacuum.fresh(90)
    await vacuum.refresh()
    clock.now += 90
    assert vacuum.fresh(90)
    clock.now += 1
    assert not vacuum.fresh(90)


async def test_status_lists_the_values(vacuum):
    await vacuum.refresh()

    status = vacuum.status()

    assert status["name"] == "robocop"
    assert status["state"] == "charging"
    assert status["battery"] == 98
    assert status["error"] == "none"
    assert status["dock_error"] == "ok"
    assert status["clean_area_m2"] == 12.5
    assert status["last_update"] == "2027-01-15T08:00:00+00:00"
    assert status["connection"] == "local"


async def test_connection_is_cloud_without_the_local_channel(vacuum, device):
    device.is_local_connected = False
    await vacuum.refresh()

    assert vacuum.status()["connection"] == "cloud"


async def test_routines_are_cached(vacuum, device, clock):
    first = await vacuum.routines()
    clock.now += 299
    await vacuum.routines()
    assert device.v1_properties.routines.fetched == 1

    clock.now += 1
    await vacuum.routines()
    assert device.v1_properties.routines.fetched == 2
    assert [routine.name for routine in first] == ["Full Cleaning", "Wohnzimmer"]


async def test_run_routine_starts_a_known_routine(vacuum, device):
    routine = await vacuum.run_routine(4207676)

    assert routine.name == "Wohnzimmer"
    assert device.v1_properties.routines.executed == [4207676]
    assert vacuum.status()["last_routine"]["name"] == "Wohnzimmer"
    assert sample(vacuum.metrics, "roborock_commands_total", {"command": "routine", "result": "success"}) == 1


async def test_run_routine_refuses_an_unknown_id(vacuum, device):
    with pytest.raises(UnknownRoutine):
        await vacuum.run_routine(1)

    assert device.v1_properties.routines.executed == []


async def test_stop_and_dock_send_their_commands(vacuum, device):
    await vacuum.stop()
    await vacuum.dock()

    assert device.v1_properties.command.sent == ["app_stop", "app_charge"]


async def test_a_command_refreshes_the_status(vacuum, device, clock):
    await vacuum.refresh()
    clock.now += 10

    await vacuum.dock()

    assert vacuum.last_refresh == clock.now


@pytest.mark.parametrize(
    "state",
    [RoborockStateCode.cleaning, RoborockStateCode.segment_cleaning, RoborockStateCode.returning_home],
)
async def test_pause_while_working(vacuum, device, state):
    device.v1_properties.status.state = state
    await vacuum.refresh()

    assert vacuum.status()["can_pause"] is True
    await vacuum.pause()

    assert device.v1_properties.command.sent == ["app_pause"]
    assert sample(vacuum.metrics, "roborock_commands_total", {"command": "pause", "result": "success"}) == 1


@pytest.mark.parametrize(
    "state",
    [RoborockStateCode.charging, RoborockStateCode.idle, RoborockStateCode.paused, RoborockStateCode.error],
)
async def test_pause_is_not_possible_while_not_working(vacuum, device, state):
    device.v1_properties.status.state = state
    await vacuum.refresh()

    assert vacuum.status()["can_pause"] is False
    with pytest.raises(NotPossible):
        await vacuum.pause()

    assert device.v1_properties.command.sent == []


@pytest.mark.parametrize(
    ("in_cleaning", "in_returning", "command"),
    [
        (RoborockInCleaning.global_clean_not_complete, 0, "app_start"),
        (RoborockInCleaning.zone_clean_not_complete, 0, "resume_zoned_clean"),
        (RoborockInCleaning.segment_clean_not_complete, 1, "resume_segment_clean"),
        (RoborockInCleaning.complete, 1, "app_charge"),
    ],
)
async def test_resume_continues_the_paused_task(vacuum, device, in_cleaning, in_returning, command):
    status = device.v1_properties.status
    status.state = RoborockStateCode.paused
    status.in_cleaning = in_cleaning
    status.in_returning = in_returning
    await vacuum.refresh()

    assert vacuum.status()["can_resume"] is True
    await vacuum.resume()

    assert device.v1_properties.command.sent == [command]


async def test_resume_without_a_task_is_not_possible(vacuum, device):
    device.v1_properties.status.state = RoborockStateCode.paused
    await vacuum.refresh()

    assert vacuum.status()["can_resume"] is False
    with pytest.raises(NotPossible):
        await vacuum.resume()


async def test_resume_is_not_possible_while_cleaning(vacuum, device):
    status = device.v1_properties.status
    status.state = RoborockStateCode.cleaning
    status.in_cleaning = RoborockInCleaning.global_clean_not_complete
    await vacuum.refresh()

    assert vacuum.status()["can_resume"] is False


async def test_pause_and_resume_are_not_possible_while_unreachable(vacuum, device):
    device.v1_properties.status.state = RoborockStateCode.cleaning
    await vacuum.refresh()
    device.v1_properties.status.fail = True
    await vacuum.refresh()

    assert vacuum.status()["can_pause"] is False
    with pytest.raises(NotPossible, match="unreachable"):
        await vacuum.pause()


async def test_a_failed_command_is_counted(vacuum, device):
    device.v1_properties.command.fail = True

    with pytest.raises(RoborockException):
        await vacuum.dock()

    assert sample(vacuum.metrics, "roborock_commands_total", {"command": "dock", "result": "failure"}) == 1


async def test_commands_without_a_device_fail_and_are_counted(clock):
    vacuum = Vacuum(Metrics(), clock)

    with pytest.raises(RoborockException):
        await vacuum.stop()

    assert sample(vacuum.metrics, "roborock_commands_total", {"command": "stop", "result": "failure"}) == 1


def test_command_counters_start_at_zero(clock):
    metrics = Metrics()

    for command in COMMANDS:
        for result in ("success", "failure"):
            assert sample(metrics, "roborock_commands_total", {"command": command, "result": result}) == 0


def test_cloud_rejection_is_a_metric(vacuum):
    assert sample(vacuum.metrics, "roborock_cloud_auth_ok") == 1

    vacuum.cloud_rejected()

    assert sample(vacuum.metrics, "roborock_cloud_auth_ok") == 0
