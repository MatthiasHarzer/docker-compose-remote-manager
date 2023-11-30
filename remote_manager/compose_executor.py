import subprocess

from remote_manager.config import Service


class ComposeExecutor:
    def __init__(self, service: Service):
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

    def status(self) -> bool:
        """
        Get the status of the service.
        :return:
        """
        return subprocess.run(self._build_cmd("ps", "--services", "--filter", "status=running"),
                              stdout=subprocess.PIPE).stdout.decode().strip() != ""

    def get_logs(self) -> list[str]:
        """
        Get the logs of the service.
        :return:
        """
        return subprocess.run(self._build_cmd("logs", "--tail", "500"), stdout=subprocess.PIPE).stdout.decode().split(
            "\n")

    def get_log_process(self) -> subprocess.Popen:
        """
        Get the process that reads the logs.
        :return:
        """
        return subprocess.Popen(self._build_cmd("logs", "-f", "--tail", "500"), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
