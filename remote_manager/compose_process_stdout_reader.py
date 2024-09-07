import subprocess
from _thread import start_new_thread
from typing import Callable

from remote_manager.compose_parsing import parse_compose_log_line, ParsedComposeLogLine

OnReadLineCallback = Callable[[ParsedComposeLogLine], None]
OnCloseCallback = Callable[[], None]
UnregisterCallback = Callable[[], None]


class ComposeProcessStdoutReader:
    """
    A threaded stdout reader for a process that notifies observers when a new line is read.
    """

    def __init__(self, process: subprocess.Popen):
        """
        Initialize the ProcessStdoutReader instance.

        This method starts a new thread that reads the stdout of the given process line by line.
        It also initializes the lists for storing the lines read from stdout and the observer callbacks.
        The process is not closed after initialization.

        Args:
            process (subprocess.Popen): The process whose stdout is to be read.

        """
        self.process = process
        self._thread = start_new_thread(self._read_stdout, ())
        self._lines: list[ParsedComposeLogLine] = []
        self._observers: list[OnReadLineCallback] = []
        self._on_close: list[OnCloseCallback] = []
        self._closed = False

    def on_read_line(self, callback: OnReadLineCallback, included_number_of_old_lines: int = 0) -> UnregisterCallback:
        """
        Register a callback that will be called when a new line is read.
        :param callback:  The callback
        :param included_number_of_old_lines: The number of old lines that should be included in the callback
        """
        self._observers.append(callback)

        for line in self._lines[-included_number_of_old_lines:]:
            callback(line)

        return lambda: self._observers.remove(callback)

    def on_close(self, callback: OnCloseCallback) -> UnregisterCallback:
        """
        Register a callback that will be called when the process is closed.
        :param callback: The callback
        """
        self._on_close.append(callback)

        return lambda: self._on_close.remove(callback)

    def stop(self) -> None:
        """
        Stop the reader.
        """
        self.process.kill()
        if not self._closed:  # Prevent calling the callback twice
            for callback in self._on_close:
                callback()
        self._closed = True

    def add_system_log_line(self, line: ParsedComposeLogLine) -> None:
        """
        Add a system log line to the list of lines read.
        :param line: The line to add
        """
        self._lines.append(line)
        self._notify_observers(line)

    def _notify_observers(self, line: ParsedComposeLogLine) -> None:
        for observer in self._observers:
            observer(line)

    def _read_stdout(self):
        while True:
            line = self.process.stdout.readline()
            if not line and self.process.poll() is not None:
                continue
            line = line.decode("utf-8").strip()
            parsed_line = parse_compose_log_line(line)
            self._lines.append(parsed_line)
            self._notify_observers(parsed_line)
