"""Isolated auth tests. Never opens the production database or calls SED."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

TEMP = tempfile.TemporaryDirectory(prefix="biblio-auth-")
os.environ["BIBLIO_DB"] = str(Path(TEMP.name) / "test.db")
os.environ["SED_ENABLED"] = "false"
os.environ["TURNSTILE_SECRET_KEY"] = ""
os.environ.pop("TOKEN_TTL_MIN", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from fastapi.testclient import TestClient
import main
import db
import auth

ORIGIN = "https://library.autoava.us"
COOKIE = "__Host-biblio_session"

class PersistentAuth(unittest.TestCase):
    def setUp(self):
        db.init_db()
        auth._tentativas.clear()
        self.client = TestClient(main.app, base_url=ORIGIN)

    def login(self):
        csrf = self.client.get('/api/auth/csrf')
        self.assertEqual(csrf.status_code, 200)
        self.headers = {'Origin': ORIGIN, 'X-CSRF-Token': csrf.json()['csrf_token']}
        response = self.client.post('/api/auth/login', headers=self.headers,
                                    json={'ra':'987654321','senha':'aluno123'})
        self.assertEqual(response.status_code, 200, response.text)
        return response

    def test_cookie_persistence_and_no_json_secret(self):
        response = self.login()
        self.assertNotIn('token', response.json())
        cookie = response.headers['set-cookie']
        for flag in ['HttpOnly', 'Secure', 'SameSite=lax', 'Max-Age=2592000', 'Path=/']:
            self.assertIn(flag, cookie)
        self.assertNotIn('Domain=', cookie)
        self.assertEqual(self.client.get('/api/auth/me').status_code, 200)
        with TestClient(main.app, base_url=ORIGIN) as reopened:
            reopened.cookies.update(self.client.cookies)
            self.assertEqual(reopened.get('/api/auth/me').status_code, 200)

if __name__ == '__main__':
    unittest.main(verbosity=2)
