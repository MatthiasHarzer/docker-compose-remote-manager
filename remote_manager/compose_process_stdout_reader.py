import subprocess
from threading import Thread
from typing import Callable

from remote_manager.compose_parsing import parse_compose_log_line, ComposeLogLine

OnReadLineCallback = Callable[[ComposeLogLine], None]
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
        self._thread = Thread(target=self._read_stdout, daemon=True)
        self._observers: list[OnReadLineCallback] = []
        self._on_close: list[OnCloseCallback] = []
        self._closed = False
        self._thread.start()

    def on_read_line(self, callback: OnReadLineCallback) -> UnregisterCallback:
        """
        Register a callback that will be called when a new line is read.
        :param callback:  The callback
        """
        self._observers.append(callback)
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

    def _notify_observers(self, line: ComposeLogLine) -> None:
        for observer in self._observers:
            observer(line)

    def _read_stdout(self):
        while True:
            line = self.process.stdout.readline()
            if not line and self.process.poll() is not None:
                break
            decoded_line = line.decode("utf-8").strip()
            parsed_line = parse_compose_log_line(decoded_line)

            if not parsed_line:
                continue
            self._notify_observers(parsed_line)

        self.stop()
