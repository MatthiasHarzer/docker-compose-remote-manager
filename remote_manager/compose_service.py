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

    @staticmethod
    def all() -> list[AccessKeyScope]:
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
    scopes: list[AccessKeyScope] = field(default_factory=AccessKeyScope.all)

    def allows(self, scope: AccessKeyScope) -> bool:
        """
        Check if the access key allows the given scope.
        :param scope:
        :return:
        """
        return scope in self.scopes or AccessKeyScope.MANAGE in self.scopes


@dataclass
class ComposeService:
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
            return AccessKeyScope.all()

        for key in self.access_keys:
            if key.value != access_key:
                continue

            return key.scopes

        return []

