from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from remote_manager.compose_parsing import ComposeLogLine, parse_compose_log_lines
from remote_manager.compose_process_stdout_reader import ComposeProcessStdoutReader
from remote_manager.observable import Observable

LOG_LINE_LIMIT = os.environ.get("LOG_LINE_LIMIT", 2000)


class AccessKeyScope(StrEnum):
    """
    The scope of an access key.
    """
    MANAGE = "manage"
    LOGS = "logs"
    STATUS = "status"

    @staticmethod
    def all() -> list[AccessKeyScope]:
        """
        Get all access key scopes.
        :return:
        """
        return [AccessKeyScope.MANAGE, AccessKeyScope.LOGS, AccessKeyScope.STATUS]

@dataclass
class AccessKey:
    """
    An access key that can restrict access to services.
    """
    value: str
    scopes: list[AccessKeyScope] = field(default_factory=AccessKeyScope.all)

    def allows(self, scope: AccessKeyScope) -> bool:
        """
        Check if the access key allows the given scope.
        :param scope:
        :return:
        """
        return scope in self.scopes or AccessKeyScope.MANAGE in self.scopes


class ComposeCli:
    def __init__(self, service: ComposeService):
        self.service = service

    @property
    def cwd(self) -> str:
        return self.service.cwd

    @property
    def compose_file(self) -> str:
        return self.cwd + "/" + self.service.compose_file

    def _build_cmd(self, *cmd: str) -> list[str]:
        return ["docker", "compose", "-f", self.compose_file, *cmd]

    def start(self) -> None:
        """
        Start the service.
        :return:
        """
        subprocess.run(self._build_cmd("up", "-d"))

    def stop(self) -> None:
        """
        Stop the service.
        :return:
        """
        subprocess.run(self._build_cmd("down"))

    def running(self) -> bool:
        """
        Get the status of the service.
        :return:
        """
        return subprocess.run(self._build_cmd("ps", "--services", "--filter", "status=running"),
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().strip() != ""

    def get_logs(self, tail: int = 250) -> list[ComposeLogLine]:
        """
        Get the logs of the service.
        :return:
        """
        lines = subprocess.run(self._build_cmd("logs", f"--tail={tail}", "-t"), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().split(
            "\n")
        return parse_compose_log_lines(lines)

    def get_log_process(self) -> subprocess.Popen:
        """
        Get the process that reads the logs.
        :return:
        """
        return subprocess.Popen(self._build_cmd("logs", "-f", "--tail=0", "-t"), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)


@dataclass
class ComposeService(Observable[ComposeLogLine]):
    name: str
    cwd: str
    compose_file: str = "docker-compose.yml"
    access_keys: list[AccessKey] | None = None
    logs: list[ComposeLogLine] = field(default_factory=list)
    std_out_reader: ComposeProcessStdoutReader | None = None

    @property
    def _cli(self) -> ComposeCli:
        return ComposeCli(self)

    def __post_init__(self):
        if self._cli.running():
            self._register_std_out_reader()
            self.logs = self._cli.get_logs(LOG_LINE_LIMIT)

    def _register_std_out_reader(self):
        if self.std_out_reader:
            return

        self.std_out_reader = ComposeProcessStdoutReader(self._cli.get_log_process())
        self.std_out_reader.on_read_line(self.add_log_line)
        self.std_out_reader.on_close(self._unregister_std_out_reader)

    def _unregister_std_out_reader(self):
        if self.std_out_reader:
            self.std_out_reader = None

    def allows(self, access_key: str, scope: AccessKeyScope | None = None) -> bool:
        """
        Check if the service allows the given access key and scope.
        :param access_key:
        :param scope: The scope to check. If None, checks any scope.
        :return:
        """

        if not self.access_keys:
            return True

        for key in self.access_keys:
            if key.value != access_key:
                continue

            if scope is None:
                return True

            if key.allows(scope):
                return True

        return False

    def get_access_key_allowed_scopes(self, access_key: str) -> list[AccessKeyScope]:
        """
        Get the scopes allowed by the access key.
        :param access_key:
        :return:
        """
        if not self.access_keys:
            return AccessKeyScope.all()

        for key in self.access_keys:
            if key.value != access_key:
                continue

            return key.scopes

        return []

    def add_log_line(self, line: ComposeLogLine) -> None:
        """
        Add a log line to the service.
        :param line:
        """
        self.logs.append(line)
        self.logs = self.logs[-LOG_LINE_LIMIT:]
        self.notify(line)

    def add_system_log_line(self, line: str) -> None:
        """
        Add a system log line to the service.
        :param line:
        """
        now = datetime.now()
        compose_line = ("system", now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), f"{line}")
        self.add_log_line(compose_line)

    def start(self) -> None:
        """
        Start the service.
        :return:
        """
        self._cli.start()
        self._register_std_out_reader()

    def stop(self) -> None:
        """
        Stop the service.
        :return:
        """
        self._cli.stop()
        self._unregister_std_out_reader()

    def running(self) -> bool:
        """
        Get the status of the service.
        :return:
        """
        running = self._cli.running()
        if running and not self.std_out_reader:
            self._register_std_out_reader()
        return running

    def get_logs(self) -> list[ComposeLogLine]:
        """
        Get the logs of the service.
        :return:
        """
        return self.logs

