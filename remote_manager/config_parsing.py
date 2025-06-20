import uuid

from remote_manager.compose_service import AccessKey, AccessKeyScope, Command, CommandsOption, ComposeService

command_id = 0


def _resolve_access_key_or_var(access_key: str, available_access_keys: dict[str, str]) -> str:
    """
    Resolve an access key to its value.
    :param access_key:
    :param available_access_keys:
    :return:
    """
    if not access_key.startswith("$"):
        return access_key
    elif access_key.startswith("$$"):
        return access_key[1:]

    key = access_key[1:]

    resolved_key = available_access_keys.get(key)

    if not resolved_key:
        raise ValueError(f"Access key {key} not found")

    return resolved_key


def parse_access_key(json: dict | str, available_keys: dict[str, str]) -> AccessKey:
    if isinstance(json, str):
        key = _resolve_access_key_or_var(json, available_keys)
        return AccessKey(key)

    scopes = json.get("scopes", AccessKeyScope.all())
    if not isinstance(scopes, list):
        scopes = [scopes]

    key = _resolve_access_key_or_var(json.get("key"), available_keys)
    return AccessKey(key, scopes)


def parse_access_keys(keys: list[str] | str | None, available_keys: dict[str, str]) -> list[AccessKey]:
    if not keys:
        return []

    if isinstance(keys, str):
        keys = [keys]

    return [parse_access_key(k, available_keys) for k in keys]


def parse_command(json: dict) -> Command | None:
    sub_service = json.get("sub-service")
    command = json.get("command", "")
    label = json.get("label")

    if not sub_service:
        return None

    if isinstance(command, str):
        command = [command]
    if command is True:
        command = []
    elif command is False:
        return None

    return Command(str(uuid.uuid4()), sub_service, command, label)


def parse_commands(json: list | bool) -> CommandsOption:
    if json is False:
        return False
    if json is True:
        return True

    commands: CommandsOption = []

    for item in json:
        if parsed := parse_command(item):
            commands.append(parsed)

    return commands


def parse_service(name: str, json: dict, available_access_keys: dict[str, str] = None) -> ComposeService:
    available_access_keys = available_access_keys or {}
    cwd = json.get("cwd")
    compose_file = json.get("compose-file", "docker-compose.yml")
    commands = json.get("commands", False)

    parsed_commands = parse_commands(commands)
    access_keys = parse_access_keys(json.get("access-key"), available_access_keys)

    return ComposeService(name, cwd, compose_file, access_keys, parsed_commands)


def parse_config(json: dict) -> dict[str, ComposeService]:
    access_keys = json.get("access-keys", {})

    services: dict[str, ComposeService] = {}
    for name, service_json in json.get("services", {}).items():
        services[name] = parse_service(name, service_json, access_keys)

    return services
