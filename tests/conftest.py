import keyring
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from PyQt6 import QtCore
import pytest


class MemoryKeyring(KeyringBackend):
    """Keeps test credentials in memory so no test touches the real keychain."""

    priority = 1

    def __init__(self):
        super().__init__()
        self.entries = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        if self.entries.pop((service, username), None) is None:
            raise PasswordDeleteError(username)


@pytest.fixture(autouse=True)
def isolated_keyring():
    previous = keyring.get_keyring()
    memory = MemoryKeyring()
    keyring.set_keyring(memory)
    yield memory
    keyring.set_keyring(previous)


@pytest.fixture(autouse=True)
def isolated_settings():
    """Settings go to Qt's test folder, never the user's real preferences."""
    QtCore.QStandardPaths.setTestModeEnabled(True)
    yield
    QtCore.QStandardPaths.setTestModeEnabled(False)
