import os
import tempfile
import unittest

from app.auth import UserStore
from app.demo_data import build_demo_queue, calculate_demo_kpis
from app.runtime import RuntimeConfig


class RuntimeTests(unittest.TestCase):
    def test_demo_defaults_disable_live_writes(self):
        old = dict(os.environ)
        try:
            os.environ['APP_ENV'] = 'demo'
            os.environ['DEMO_MODE_DEFAULT'] = 'true'
            os.environ['ALLOW_LIVE_WRITES'] = 'false'
            config = RuntimeConfig.from_env()
            self.assertTrue(config.is_demo)
            self.assertTrue(config.demo_mode_default)
            self.assertFalse(config.allow_live_writes)
            with self.assertRaises(PermissionError):
                config.require_live_writes_enabled()
        finally:
            os.environ.clear()
            os.environ.update(old)


class AuthTests(unittest.TestCase):
    def test_demo_users_can_be_created_and_authenticated(self):
        old = dict(os.environ)
        try:
            os.environ['APP_ENV'] = 'demo'
            os.environ['DEMO_ADMIN_PASSWORD'] = 'admin-password-123'
            os.environ['DEMO_USER_PASSWORD'] = 'user-password-123'
            with tempfile.TemporaryDirectory() as tmp:
                store = UserStore(path=f'{tmp}/users.json')
                store.ensure_demo_users()
                admin = store.authenticate('admin', 'admin-password-123')
                sales = store.authenticate('sales', 'user-password-123')
                self.assertIsNotNone(admin)
                self.assertEqual(admin.role, 'admin')
                self.assertIsNotNone(sales)
                self.assertEqual(sales.role, 'user')
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_production_requires_explicit_initial_passwords(self):
        old = dict(os.environ)
        try:
            os.environ['APP_ENV'] = 'production'
            os.environ.pop('DEMO_ADMIN_PASSWORD', None)
            os.environ.pop('DEMO_USER_PASSWORD', None)
            with tempfile.TemporaryDirectory() as tmp:
                store = UserStore(path=f'{tmp}/users.json')
                with self.assertRaises(RuntimeError):
                    store.ensure_demo_users()
        finally:
            os.environ.clear()
            os.environ.update(old)


class DemoDataTests(unittest.TestCase):
    def test_demo_queue_has_kpis(self):
        queue = build_demo_queue()
        kpis = calculate_demo_kpis(queue)
        self.assertGreaterEqual(len(queue), 1)
        self.assertEqual(kpis['messages_analyzed'], len(queue))
        self.assertGreaterEqual(kpis['proposed_actions'], 1)


if __name__ == '__main__':
    unittest.main()
