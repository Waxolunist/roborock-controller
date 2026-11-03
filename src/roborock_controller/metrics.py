from prometheus_client import CollectorRegistry, Counter, Gauge

COMMANDS = ("routine", "stop", "dock", "pause", "resume")


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.up = Gauge("roborock_up", "1 while the last status refresh succeeded", registry=self.registry)
        self.cloud_auth_ok = Gauge(
            "roborock_cloud_auth_ok", "0 once the Roborock cloud rejected the credentials", registry=self.registry
        )
        self.local_connection = Gauge(
            "roborock_local_connection", "1 while the vacuum is reached over the local network", registry=self.registry
        )
        self.last_refresh = Gauge(
            "roborock_last_refresh_timestamp_seconds",
            "Time of the last successful status refresh",
            registry=self.registry,
        )
        self.battery = Gauge("roborock_battery_percent", "Battery level", registry=self.registry)
        self.state = Gauge("roborock_state", "1 for the current state", ["state"], registry=self.registry)
        self.error_code = Gauge("roborock_error_code", "Vacuum error code, 0 without error", registry=self.registry)
        self.error = Gauge("roborock_error", "1 for the current vacuum error", ["error"], registry=self.registry)
        self.dock_error_code = Gauge(
            "roborock_dock_error_code", "Dock error code, 0 without error", registry=self.registry
        )
        self.dock_error = Gauge(
            "roborock_dock_error", "1 for the current dock error", ["error"], registry=self.registry
        )
        self.commands = Counter(
            "roborock_commands", "Commands sent to the vacuum", ["command", "result"], registry=self.registry
        )
        for command in COMMANDS:
            for result in ("success", "failure"):
                self.commands.labels(command, result)
        self.cloud_auth_ok.set(1)
        self.up.set(0)
        self.local_connection.set(0)

    def status(self, status, local: bool, timestamp: float) -> None:
        self.up.set(1)
        self.local_connection.set(int(local))
        self.last_refresh.set(timestamp)
        if status.battery is not None:
            self.battery.set(status.battery)
        _set_one(self.state, status.state_name)
        self.error_code.set(_code(status.error_code))
        _set_one(self.error, _name(status.error_code))
        self.dock_error_code.set(_code(status.dock_error_status))
        _set_one(self.dock_error, _name(status.dock_error_status))

    def unreachable(self) -> None:
        self.up.set(0)
        self.local_connection.set(0)

    def command(self, command: str, success: bool) -> None:
        self.commands.labels(command, "success" if success else "failure").inc()


def _set_one(gauge: Gauge, label: str | None) -> None:
    gauge.clear()
    if label is not None:
        gauge.labels(label).set(1)


def _code(value) -> int:
    return 0 if value is None else int(value.value)


def _name(value) -> str | None:
    return None if value is None else value.name
