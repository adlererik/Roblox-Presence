import os
import stat
import struct
from unittest.mock import patch

from roblox_presence.config import ConfigError, secret, systemd_acl_private
from tests.test_monitor import Fixture


class ManagedCredentialTests(Fixture):
    service_uid = 1337

    def acl(self, users=None, group=0, other=0):
        entries = [(1, 4, 0xFFFFFFFF)]
        entries.extend((2, 4, uid) for uid in (users if users is not None else [self.service_uid]))
        entries.extend([(4, group, 0xFFFFFFFF), (16, 4, 0xFFFFFFFF), (32, other, 0xFFFFFFFF)])
        return struct.pack('<I', 2) + b''.join(struct.pack('<HHI', *entry) for entry in entries)

    def root_metadata(self):
        values = list(self.cookie.stat())
        values[4] = 0
        return os.stat_result(values)

    def test_native_service_acl_is_readable_without_accepting_direct_group_files(self):
        os.setxattr(self.cookie, 'system.posix_acl_access', self.acl())
        self.assertEqual(stat.S_IMODE(self.cookie.stat().st_mode), 0o440)
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)), \
                patch('roblox_presence.config.os.geteuid', return_value=self.service_uid), \
                patch('roblox_presence.config.os.fstat', return_value=self.root_metadata()):
            self.assertEqual(secret('credential:cookie'), 'TEST_OBSERVER_SESSION')
            with self.assertRaises(ConfigError):
                secret(str(self.cookie))

    def test_ordinary_group_read_file_is_rejected_even_for_managed_reference(self):
        self.cookie.chmod(0o440)
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)), \
                patch('roblox_presence.config.os.fstat', return_value=self.root_metadata()):
            with self.assertRaises(ConfigError):
                secret('credential:cookie')

    def test_acl_cannot_grant_another_user_group_or_world_access(self):
        for acl in [self.acl(users=[1338]), self.acl(users=[1337, 1338]),
                    self.acl(group=4), self.acl(other=4)]:
            os.setxattr(self.cookie, 'system.posix_acl_access', acl)
            with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)), \
                    patch('roblox_presence.config.os.geteuid', return_value=self.service_uid), \
                    patch('roblox_presence.config.os.fstat', return_value=self.root_metadata()):
                with self.assertRaises(ConfigError):
                    secret('credential:cookie')

    def test_managed_acl_snapshot_requires_root_ownership(self):
        os.setxattr(self.cookie, 'system.posix_acl_access', self.acl())
        values = list(self.cookie.stat()); values[4] = self.service_uid
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)), \
                patch('roblox_presence.config.os.geteuid', return_value=self.service_uid), \
                patch('roblox_presence.config.os.fstat', return_value=os.stat_result(values)):
            with self.assertRaises(ConfigError):
                secret('credential:cookie')

    def test_malformed_acl_is_not_accepted(self):
        self.cookie.chmod(0o440)
        for data in [b'', self.acl()[:-1], b'\x03\0\0\0' + self.acl()[4:],
                     self.acl()[:4] + self.acl()[4:12] * 5]:
            with patch('roblox_presence.config.os.getxattr', return_value=data):
                self.assertFalse(systemd_acl_private(1, self.root_metadata()))

    def test_managed_symlinks_are_still_rejected(self):
        (self.root / 'link').symlink_to(self.cookie)
        with patch.dict(os.environ, CREDENTIALS_DIRECTORY=str(self.root)):
            with self.assertRaises(ConfigError):
                secret('credential:link')
