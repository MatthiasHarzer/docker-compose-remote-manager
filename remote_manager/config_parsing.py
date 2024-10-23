from remote_manager.compose_service import AccessKey, AccessKeyScope, ComposeService, Command, CommandsOption

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

def parse_command(json: dict | str | bool) -> Command | bool:
    if json is False:
        return True
    if json is True:
        return False

    if isinstance(json, str):
        return Command([json], json)

    if isinstance(json, dict):
        command = json.get("command")
        label = json.get("label")

        if isinstance(command, str):
            command = [command]

        return Command(command, label)

    return False

def parse_commands(json: dict | bool) -> CommandsOption:
    if json is False:
        return False
    if json is True:
        return True

    commands: CommandsOption = {}

    for name, command_json in json.items():
        commands[name] = parse_command(command_json)

    return commands

def parse_service(name: str, json: dict, available_access_keys: dict[str, AccessKey] = None) -> ComposeService:
    available_access_keys = available_access_keys or {}
    cwd = json.get("cwd")
    compose_file = json.get("compose-file", "docker-compose.yml")
    commands = json.get("commands", False)

    parsed_commands = parse_commands(commands)


    keys: list[str] | str | None = json.get("access-key")
    if keys and not isinstance(keys, list):
        keys = [keys]

    access_keys = None
    if keys:
        access_keys = [parse_access_key(k, available_access_keys) for k in keys]

    return ComposeService(name, cwd, compose_file, access_keys, parsed_commands)

def parse_config(json: dict) -> dict[str, ComposeService]:
    access_keys = json.get("access-keys", {})

    services: dict[str, ComposeService] = {}
    for name, service_json in json.get("services", {}).items():
        services[name] = parse_service(name, service_json, access_keys)

    return services
