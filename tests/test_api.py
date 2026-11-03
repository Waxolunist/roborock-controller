import pytest
from aiohttp.test_utils import TestClient, TestServer
from roborock.data import RoborockInCleaning, RoborockStateCode

from roborock_controller.api import api_app, metrics_app
from roborock_controller.metrics import Metrics
from roborock_controller.vacuum import Vacuum
from tests.fakes import FakeClock, FakeDevice


@pytest.fixture
def device():
    return FakeDevice()


@pytest.fixture
def vacuum(device):
    vacuum = Vacuum(Metrics(), FakeClock(), settle_seconds=0)
    vacuum.attach(device)
    return vacuum


@pytest.fixture
async def client(vacuum):
    async with TestClient(TestServer(api_app(vacuum, 90))) as client:
        yield client


async def test_health_is_503_before_the_first_refresh(client):
    response = await client.get("/health")

    assert response.status == 503


async def test_health_is_200_after_a_refresh(client, vacuum):
    await vacuum.refresh()

    response = await client.get("/health")

    assert response.status == 200


async def test_status(client, vacuum):
    await vacuum.refresh()

    body = await (await client.get("/status")).json()

    assert body["state"] == "charging"
    assert body["battery"] == 98
    assert body["can_pause"] is False
    assert body["can_resume"] is False


async def test_routines(client):
    body = await (await client.get("/routines")).json()

    assert body == [{"id": 4146859, "name": "Full Cleaning"}, {"id": 4207676, "name": "Wohnzimmer"}]


async def test_run_routine(client, device):
    response = await client.post("/routines/4146859")

    assert response.status == 200
    assert (await response.json()) == {"started": {"id": 4146859, "name": "Full Cleaning"}}
    assert device.v1_properties.routines.executed == [4146859]


async def test_run_unknown_routine_is_404(client, device):
    response = await client.post("/routines/42")

    assert response.status == 404
    assert device.v1_properties.routines.executed == []


async def test_routines_need_post(client, device):
    response = await client.get("/routines/4146859")

    assert response.status == 405
    assert device.v1_properties.routines.executed == []


async def test_stop_and_dock(client, device):
    assert (await client.post("/stop")).status == 200
    assert (await client.post("/dock")).status == 200

    assert device.v1_properties.command.sent == ["app_stop", "app_charge"]


async def test_pause_and_resume(client, vacuum, device):
    status = device.v1_properties.status
    status.state = RoborockStateCode.segment_cleaning
    await vacuum.refresh()
    assert (await (await client.get("/status")).json())["can_pause"] is True

    response = await client.post("/pause")
    assert response.status == 200
    assert (await response.json()) == {"sent": "pause"}

    status.state = RoborockStateCode.paused
    status.in_cleaning = RoborockInCleaning.segment_clean_not_complete
    await vacuum.refresh()
    assert (await client.post("/resume")).status == 200

    assert device.v1_properties.command.sent == ["app_pause", "resume_segment_clean"]


async def test_pause_while_docked_is_409(client, vacuum, device):
    await vacuum.refresh()

    response = await client.post("/pause")

    assert response.status == 409
    assert (await response.json()) == {"error": "pause is not possible while the vacuum is charging"}
    assert device.v1_properties.command.sent == []


async def test_a_vacuum_error_is_502(client, device):
    device.v1_properties.command.fail = True

    response = await client.post("/dock")

    assert response.status == 502
    assert (await response.json()) == {"error": "device busy"}


async def test_metrics(vacuum):
    await vacuum.refresh()
    async with TestClient(TestServer(metrics_app(vacuum))) as client:
        response = await client.get("/metrics")
        text = await response.text()

    assert response.status == 200
    assert response.content_type == "text/plain"
    assert "roborock_battery_percent 98.0" in text
