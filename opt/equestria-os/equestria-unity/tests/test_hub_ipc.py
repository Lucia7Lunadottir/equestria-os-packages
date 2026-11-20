import json
import shutil
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import hub_ipc

USER = {"foreignKey": "100", "name": "Twilight Sparkle", "email": "twilight@example.org", "primaryOrg": "canterlot"}


class FakeCli:
    """The Unity CLI answers the service reads, without a process."""

    def __init__(self, signed_in=True):
        self.signed_in = signed_in
        self.token = "token-1"   # None: the CLI does not answer (password prompt cancelled, no answer in time)
        self.calls = []

    def query(self, arguments, timeout=0, interactive=False):
        self.calls.append(arguments)
        if arguments == ["auth", "accounts"]:
            return {"accounts": [USER], "activeForeignKey": "100"} if self.signed_in else {"accounts": []}
        if arguments == ["cloud", "orgs"]:
            return {"organizations": [{"id": "uuid-1", "genesisId": "200", "name": "Canterlot", "role": "owner"}]}
        return None

    def token_info(self, timeout=0):
        self.calls.append(["auth", "token"])
        if not self.signed_in or not self.token:
            return None
        return {"accessToken": self.token, "expiresAt": "2030-01-01T00:00:00Z"}


class HubIpcTests(unittest.TestCase):
    def setUp(self):
        folder = Path(tempfile.mkdtemp(dir="/tmp", prefix="hub"))   # socket paths must stay short
        self.addCleanup(shutil.rmtree, folder, True)
        self.path = folder / "s.sock"
        self.enterContext(patch.object(hub_ipc.OrganizationDirectory, "slugs", return_value={"200": "canterlot"}))
        self.enterContext(patch.object(hub_ipc, "LOG", folder / "log"))

    def start(self, cli):
        service = hub_ipc.HubIpcService(self.path, hub_ipc.AccountSource(cli))
        threading.Thread(target=service.serve, daemon=True).start()
        deadline = time.monotonic() + 5
        while not self.path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        return service

    def connect(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(5)
        client.connect(str(self.path))
        self.addCleanup(client.close)
        return client

    @staticmethod
    def receive(client, count):
        buffer = b""
        while buffer.count(b"\f") < count:
            buffer += client.recv(65536)
        return [json.loads(frame) for frame in buffer.split(b"\f")[:count]]

    def test_answers_like_the_hub(self):
        self.start(FakeCli())
        client = self.connect()
        # Two requests in one write and one split across writes: frames end at the form feed, not at a read.
        client.sendall(b'{ "type":"config:get", "data":{}}\f{ "type":"connectInfo:get", "data":{}}\f{ "type":"user')
        client.sendall(b'Info:get", "data":{}}\f{ "type":"orgInfo:get", "data":{}}\f')
        config, connect, user, orgs = self.receive(client, 4)
        self.assertEqual(config["type"], "config:get")
        self.assertEqual(config["data"]["identity"], "https://api.unity.com")
        self.assertEqual(connect, {"type": "connectInfo:changed", "data": {
            "error": False, "initialized": True, "loggedIn": True, "maintenance": False, "online": True,
            "ready": True, "showLoginWindow": False, "workOffline": False}})
        self.assertEqual(user["type"], "userInfo:changed")
        self.assertEqual({k: user["data"][k] for k in ("userId", "displayName", "name", "primaryOrg", "accessToken",
                                                       "valid")},
                         {"userId": "100", "displayName": "Twilight Sparkle", "name": "twilight@example.org",
                          "primaryOrg": "canterlot", "accessToken": "token-1", "valid": True})
        self.assertEqual(user["data"]["accessTokenExpiration"], 1893456000000)
        self.assertEqual(orgs, {"type": "orgInfo:changed", "data": [
            {"name": "Canterlot", "role": "owner", "org_identifier": "uuid-1", "billable_user_fk": 100,
             "id": "canterlot", "foreign_key": "200"}]})

    def test_signed_out_and_a_new_token_is_pushed(self):
        cli = FakeCli(signed_in=False)
        service = self.start(cli)
        client = self.connect()
        client.sendall(b'{"type":"userInfo:get","data":{}}\f{"type":"connectInfo:get","data":{}}\f')
        user, connect = self.receive(client, 2)
        self.assertFalse(user["data"]["valid"])
        self.assertEqual(user["data"]["accessToken"], "")
        self.assertFalse(connect["data"]["loggedIn"])

        cli.signed_in = True          # signed in elsewhere: every Editor hears it without asking
        self.assertTrue(service.source.refresh())
        service.push()
        pushed = {m["type"]: m["data"] for m in self.receive(client, 3)}
        self.assertTrue(pushed["connectInfo:changed"]["loggedIn"])
        self.assertEqual(pushed["userInfo:changed"]["accessToken"], "token-1")
        self.assertEqual(pushed["orgInfo:changed"][0]["id"], "canterlot")

    def test_token_close_to_expiry_is_due(self):
        source = hub_ipc.AccountSource(FakeCli())
        source.refresh()
        self.assertFalse(source.due())
        source.current.expires_ms = int((time.time() + 60) * 1000)
        self.assertTrue(source.due())

    def test_a_failed_renewal_is_not_a_sign_out_and_is_not_retried(self):
        cli = FakeCli()
        source = hub_ipc.AccountSource(cli)
        source.refresh()
        source.current.expires_ms = int((time.time() + 60) * 1000)
        self.assertTrue(source.due())
        cli.token = None                  # the renewal asked for the password and the prompt was cancelled
        self.assertFalse(source.refresh())
        self.assertTrue(source.snapshot(0).signed_in)   # the Editors keep the account they had
        self.assertEqual(source.snapshot(0).token, "token-1")
        cli.calls.clear()
        self.assertFalse(source.due())    # no new prompt by itself for the same token
        self.assertNotIn(["auth", "token"], cli.calls)

    def test_periodic_check_does_not_touch_the_token(self):
        cli = FakeCli()
        source = hub_ipc.AccountSource(cli)
        source.refresh()
        source.loaded_at -= hub_ipc.RELOAD_EVERY + 1
        cli.calls.clear()
        self.assertFalse(source.due())    # same account: nothing to reload
        self.assertEqual(cli.calls, [["auth", "accounts"]])
        cli.signed_in = False
        source.loaded_at -= hub_ipc.RELOAD_EVERY + 1
        self.assertTrue(source.due())     # signed out elsewhere: reload and tell the Editors

    def test_does_not_take_a_socket_somebody_answers(self):
        other = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(other.close)
        other.bind(str(self.path))
        other.listen()
        self.assertIsNone(hub_ipc.HubIpcService(self.path, hub_ipc.AccountSource(FakeCli())).bind())

    def test_stale_socket_is_replaced_and_private(self):
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(self.path))
        stale.close()                 # the file stays, nobody listens: a crashed service
        server = hub_ipc.HubIpcService(self.path, hub_ipc.AccountSource(FakeCli())).bind()
        self.addCleanup(server.close)
        self.assertIsNotNone(server)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_another_users_editor_is_refused(self):
        self.start(FakeCli())
        with patch.object(hub_ipc.HubIpcService, "same_user", return_value=False):
            client = self.connect()
            try:
                client.sendall(b'{"type":"userInfo:get","data":{}}\f')
                reply = client.recv(100)
            except ConnectionResetError:
                reply = b""
            self.assertEqual(reply, b"")   # closed without a word, the token never sent


if __name__ == "__main__":
    unittest.main()
