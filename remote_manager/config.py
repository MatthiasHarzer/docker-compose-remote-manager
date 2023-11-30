from __future__ import annotations

from dataclasses import dataclass


def _resolve_access_key(access_key: str, available_access_keys: dict[str, str]) -> str:
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


@dataclass
class Service:
    name: str
    cwd: str
    compose_file: str = "docker-compose.yml"
    access_keys: list[str] | None = None

    def allows(self, access_key: str) -> bool:
        """
        Check if the service allows the given access key.
        :param access_key:
        :return:
        """
        if not self.access_keys:
            return True
        return access_key in self.access_keys

    @staticmethod
    def from_json(name: str, json: dict, available_access_keys: dict[str, str] = None) -> Service:
        available_access_keys = available_access_keys or {}
        cwd = json.get("cwd")
        compose_file = json.get("compose-file", "docker-compose.yml")
        keys: list[str] | str | None = json.get("access-key")
        if keys and not isinstance(keys, list):
            keys = [keys]

        access_keys = None
        if keys:
            access_keys = [_resolve_access_key(key, available_access_keys) for key in keys]

        return Service(name, cwd, compose_file, access_keys)


@dataclass
class Config:
    access_keys: dict[str, str]
    services: dict[str, Service]

    @staticmethod
    def from_json(json: dict) -> Config:
        access_keys = json.get("access-keys", {})
        services = {k: Service.from_json(k, v, access_keys) for k, v in json.get("services", {}).items()}

        return Config(access_keys, services)
