from __future__ import annotations

import os
import subprocess
import uuid
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
    COMMANDS = "commands"

    @staticmethod
    def all() -> list[AccessKeyScope]:
        """
        Get all access key scopes.
        :return:
        """
        return [AccessKeyScope.MANAGE, AccessKeyScope.LOGS, AccessKeyScope.STATUS, AccessKeyScope.COMMANDS]

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

@dataclass
class Command:
    id: str
    sub_service: str
    command: list[str]
    label: str

    def __post_init__(self):
        if not self.label:
            self.label = " ".join(self.command)

    def get_completed_command(self, user_arg: list[str]) -> list[str]:
        """
        Get the completed command with the user argument.
        :param user_arg:
        :return: The completed command
        """
        #? Maybe add template syntax in the future?
        return self.command + user_arg

    @classmethod
    def default(cls, sub_service: str, command: list[str] | None = None) -> Command:
        command_name = "default" if not command else " ".join(command)
        return Command(str(uuid.uuid4()), sub_service, command or [], command_name)

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
        return ["docker", "--log-level", "ERROR", "compose", "-f", self.compose_file, *cmd]

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

    def get_sub_services(self) -> list[str]:
        """
        Get the sub services of the service.
        :return:
        """
        services = subprocess.run(self._build_cmd("config", "--services"), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode().split(
            "\n")
        return [s.strip() for s in services if s]

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

    def execute_command(self, sub_service: str, *command: str) -> tuple[bool, str]:
        """
        Execute a command in the service.
        :param sub_service:
        :param command:
        :return: A tuple with a boolean indicating success and the output
        """
        try:
            output = subprocess.check_output(self._build_cmd("exec", sub_service, *command), stderr=subprocess.STDOUT)
            return True, output.decode("utf-8")
        except subprocess.CalledProcessError as e:
            return False, e.output.decode("utf-8")


type CommandsOption = list[Command] | bool

class ComposeService(Observable[ComposeLogLine]):
    def __init__(self, name: str, cwd: str, compose_file: str, access_keys: list[AccessKey] | None, parsed_commands: CommandsOption):
        self.name = name
        self.cwd = cwd
        self.compose_file = compose_file
        self.access_keys = access_keys or []
        self.sub_services = self._cli.get_sub_services()
        self.commands = self._get_commands(parsed_commands)
        self.log: list[ComposeLogLine] = []
        self.std_out_reader: ComposeProcessStdoutReader | None = None
        self.__health_check__()

    @property
    def _cli(self) -> ComposeCli:
        return ComposeCli(self)

    def __health_check__(self) -> bool:
        running = self._cli.running()
        if running and not self.std_out_reader:
            self._register_std_out_reader()
            self.logs = self._cli.get_logs(LOG_LINE_LIMIT)
        elif not running and self.std_out_reader:
            self._unregister_std_out_reader()

        return running

    def _get_commands(self, parsed_commands: CommandsOption) -> list[Command]:
        if parsed_commands is False:
            return []
        if parsed_commands is True:
            return [Command(str(uuid.uuid4()), s, [], "default (std::in)") for s in self.sub_services]

        return parsed_commands


    def _get_command(self, command_id: str) -> Command | None:
        for command in self.commands:
            if command.id == command_id:
                return command

        return None

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

    def add_system_log_line(self, raw_lines: str) -> None:
        """
        Add a system log line to the service.
        :param raw_lines:
        """
        now = datetime.now()

        lines = raw_lines.split("\n")

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

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
        return self.__health_check__()

    def get_logs(self) -> list[ComposeLogLine]:
        """
        Get the logs of the service.
        :return:
        """
        self.__health_check__()
        return self.logs

    def execute_command(self, command_id: str, user_arg: list[str]) -> tuple[bool, str]:
        """
        Execute a command in the service.
        :param command_id:
        :param user_arg:
        :return:
        """

        command = self._get_command(command_id)

        if not command:
            return False, f"Command {command_id} not found"

        completed_command = command.get_completed_command(user_arg)

        return self._cli.execute_command(command.sub_service, *completed_command)

