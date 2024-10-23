import re

ComposeLogLine = tuple[str, str, str]


def parse_compose_log_line(line: str) -> ComposeLogLine | None:
    """
    Extracts the name, timestamp and log message from the original docker compose log line
    :param line:
    :return: The name, timestamp and log message
    """
    log_regex = r"([^\|]+)\|( (\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2}).(\d+)Z)? (.+)"
    match = re.findall(log_regex, line)

    if not match:
        return None

    name, full_timestamp, year, month, day, hour, minute, second, fraction, log = match[0]  # type: str

    log_no_ts = log.replace(full_timestamp, "", 1)

    if name and full_timestamp and log_no_ts:
        return name.strip(), full_timestamp.strip(), log_no_ts

    return None


def parse_compose_log_lines(lines: list[str]) -> list[ComposeLogLine]:
    """
    Extracts the name, timestamp and log message from the log lines.
    :param lines:
    :return: The name, timestamp and log message
    """
    logs = []
    for line in lines:
        log = parse_compose_log_line(line)
        if log:
            logs.append(log)
    return logs
