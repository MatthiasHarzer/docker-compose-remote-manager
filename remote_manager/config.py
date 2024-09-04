from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class AccessKeyScope(StrEnum):
    """
    The scope of an access key.
    """
    MANAGE = "manage"
    LOGS = "logs"
    STATUS = "status"


def _all_scopes() -> list[AccessKeyScope]:
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
    scopes: list[AccessKeyScope] = field(default_factory=_all_scopes)

    def allows(self, scope: AccessKeyScope) -> bool:
        """
        Check if the access key allows the given scope.
        :param scope:
        :return:
        """
        return scope in self.scopes or AccessKeyScope.MANAGE in self.scopes

    @staticmethod
    def from_json(json: dict | str, available_keys: dict[str, str]) -> AccessKey:
        if isinstance(json, str):
            key = _resolve_access_key_or_var(json, available_keys)
            return AccessKey(key)

        scopes = json.get("scopes", _all_scopes())
        if not isinstance(scopes, list):
            scopes = [scopes]

        key = _resolve_access_key_or_var(json.get("key"), available_keys)
        return AccessKey(key, scopes)


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

    def get_access_key_allowed_scopes(self, access_key: str) -> list[AccessKeyScope]:
        """
        Get the scopes allowed by the access key.
        :param access_key:
        :return:
        """
        if not self.access_keys:
            return _all_scopes()

        for key in self.access_keys:
            if key.value != access_key:
                continue

            return key.scopes

        return []

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
            access_keys = [AccessKey.from_json(k, available_access_keys) for k in keys]

        return Service(name, cwd, compose_file, access_keys)


@dataclass
class Config:
    """
    The configuration of the remote manager.
    """
    access_keys: dict[str, str]
    services: dict[str, Service]

    @staticmethod
    def from_json(json: dict) -> Config:
        access_keys = json.get("access-keys", {})

        services = {k: Service.from_json(k, v, access_keys) for k, v in json.get("services", {}).items()}

        return Config(access_keys, services)
