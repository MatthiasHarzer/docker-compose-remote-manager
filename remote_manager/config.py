from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AccessKeyScope(StrEnum):
    """
    The scope of an access key.
    """
    START_STOP = "start-stop"
    LOGS = "logs"
    STATUS = "status"


def _all_scopes() -> list[AccessKeyScope]:
    """
    Get all access key scopes.
    :return:
    """
    return [AccessKeyScope.START_STOP, AccessKeyScope.LOGS, AccessKeyScope.STATUS]


@dataclass
class AccessKey:
    """
    An access key that can restrict access to services.
    """
    name: str
    value: str
    scopes: list[AccessKeyScope] = field(default_factory=_all_scopes)

    def allows(self, scope: AccessKeyScope) -> bool:
        """
        Check if the access key allows the given scope.
        :param scope:
        :return:
        """
        return scope in self.scopes

    @staticmethod
    def from_json(name: str, json: dict | str) -> AccessKey:
        if isinstance(json, str):
            return AccessKey(name, json)

        else:
            scopes = json.get("scopes", _all_scopes())
            if not isinstance(scopes, list):
                scopes = [scopes]
            return AccessKey(name, json.get("value"), scopes)


def _resolve_access_key(access_key: str, available_access_keys: dict[str, AccessKey]) -> AccessKey:
    """
    Resolve an access key to its value.
    :param access_key:
    :param available_access_keys:
    :return:
    """
    if not access_key.startswith("$"):
        return AccessKey(access_key, access_key)
    elif access_key.startswith("$$"):
        return AccessKey(access_key[1:], access_key[1:], [])

    key = access_key[1:]

    resolved_key = available_access_keys.get(key)

    if not resolved_key:
        raise ValueError(f"Access key {key} not found")

    return resolved_key


@dataclass
class Service:
    """
    A service that defines a docker-compose service.
    """
    name: str
    cwd: str
    compose_file: str = "docker-compose.yml"
    access_keys: list[AccessKey] | None = None

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

    @staticmethod
    def from_json(name: str, json: dict, available_access_keys: dict[str, AccessKey] = None) -> Service:
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
    """
    The configuration of the remote manager.
    """
    access_keys: dict[str, AccessKey]
    services: dict[str, Service]

    def get_key_scopes(self, key: str) -> list[AccessKeyScope]:
        """
        Get the scopes of the given access key.
        :param key:
        :return:
        """
        k = self.access_keys.get(key)
        if not k:
            return []
        return k.scopes

    @staticmethod
    def from_json(json: dict) -> Config:
        json_access_keys = json.get("access-keys", {})
        access_keys = {k: AccessKey.from_json(k, v) for k, v in json_access_keys.items()}

        services = {k: Service.from_json(k, v, access_keys) for k, v in json.get("services", {}).items()}

        return Config(access_keys, services)
