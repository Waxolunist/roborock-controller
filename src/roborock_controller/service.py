import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from aiohttp import web
from roborock.devices.device_manager import create_device_manager
from roborock.devices.file_cache import FileCache
from roborock.exceptions import RoborockException, RoborockInvalidCredentials

from roborock_controller.api import api_app, metrics_app
from roborock_controller.credentials import Credentials
from roborock_controller.metrics import Metrics
from roborock_controller.vacuum import Vacuum

logger = logging.getLogger(__name__)

CONNECT_RETRY_SECONDS = 300


@dataclass
class Settings:
    secrets: Path
    cache: Path
    device_name: str | None
    api_port: int
    metrics_port: int
    refresh_seconds: int


async def serve(settings: Settings) -> None:
    vacuum = Vacuum(Metrics())
    runners = [
        await _start(api_app(vacuum, settings.refresh_seconds * 3), settings.api_port),
        await _start(metrics_app(vacuum), settings.metrics_port),
    ]
    manager = None
    try:
        manager = await _connect(vacuum, settings)
        while True:
            await vacuum.refresh()
            await asyncio.sleep(settings.refresh_seconds)
    finally:
        if manager is not None:
            await manager.close()
        for runner in runners:
            await runner.cleanup()


async def _start(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    return runner


async def _connect(vacuum: Vacuum, settings: Settings):
    credentials = Credentials.load(settings.secrets)
    settings.cache.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            manager = await create_device_manager(
                credentials.user_params(),
                cache=FileCache(settings.cache),
                mqtt_session_unauthorized_hook=vacuum.cloud_rejected,
            )
            vacuum.attach(_pick(await manager.get_devices(), settings.device_name))
            logger.info("Connected to %s", vacuum.device.name)
            return manager
        except RoborockInvalidCredentials:
            vacuum.cloud_rejected()
        except RoborockException as e:
            logger.warning("Connecting failed: %s", e)
        await vacuum.refresh()
        await asyncio.sleep(CONNECT_RETRY_SECONDS)


def _pick(devices, name: str | None):
    matching = [device for device in devices if name is None or device.name == name]
    if not matching:
        raise RoborockException(f"No vacuum named {name}" if name else "No vacuum on the account")
    return matching[0]
