#!/usr/bin/env python3
"""The Editor's account service, in place of Unity Hub.

An Editor started with -useHub -hubIPC asks a local socket for the signed-in user, the access token, the
organizations and the service addresses; without an answer it shows "You must install the Unity Hub" and
Sign in, the Asset Store, "My Assets" and cloud services stay unavailable. This process answers those
questions from the Unity CLI's session, so the Hub does not have to be installed.

Protocol (recorded from Unity Hub 4.0.1): UTF-8 JSON messages separated by a form feed. The Editor sends
{"type": "<topic>:get", "data": {}}; the answer is {"type": "<topic>:changed", "data": ...} (config:get is
answered as "config:get"). The same "changed" messages are pushed when the account or its token changes.

It runs detached from the launcher, so an open Editor keeps its account after the launcher is closed, and
exits by itself once no Editor has been connected for a while.
"""
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hub_config import PRODUCTION  # noqa: E402
from unity_cli import UnityCli  # noqa: E402

SOCKET = Path("/tmp/Unity-hubIPCService.sock")
SEPARATOR = b"\f"
MAX_FRAME = 1 << 20
IDLE_EXIT = 600         # seconds without any Editor before the service ends
RECHECK = 60            # how often the account and the token are looked at
RENEW_BEFORE = 15 * 60  # a token this close to its expiry is replaced
RELOAD_EVERY = 10 * 60  # sign-in changes made elsewhere (launcher, terminal) are picked up this often
# A token renewal is a network round trip; it may be slow, but a slow answer is not a sign-out.
TOKEN_WAIT = 120
LOG = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "equestria-unity" / "hub-ipc.log"
ORGANIZATIONS_API = "https://api.unity.com/v1/organizations?userId={}"


def log(text):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as stream:
            stream.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


class Account:
    """One snapshot of the signed-in account, already in the shapes the Editor expects."""

    def __init__(self, user=None, token=None, expires_ms=0, organizations=()):
        self.user = user or {}
        self.token = token or ""
        self.expires_ms = expires_ms
        self.organizations = list(organizations)

    @property
    def signed_in(self):
        return bool(self.user and self.token)

    def expires_in(self):
        return self.expires_ms / 1000 - time.time()

    def user_info(self):
        if not self.signed_in:
            return {"userId": "", "displayName": "", "name": "", "primaryOrg": "", "accessToken": "",
                    "accessTokenExpiration": 0, "valid": False, "whitelisted": True,
                    "organizationForeignKeys": "", "cached": False}
        return {"userId": self.user.get("foreignKey", ""), "displayName": self.user.get("name", ""),
                "name": self.user.get("email", ""), "primaryOrg": self.user.get("primaryOrg", ""),
                "accessToken": self.token, "accessTokenExpiration": self.expires_ms, "valid": True,
                "whitelisted": True, "organizationForeignKeys": "", "cached": False}

    def connect_info(self):
        return {"error": False, "initialized": True, "loggedIn": self.signed_in, "maintenance": False,
                "online": True, "ready": True, "showLoginWindow": False, "workOffline": False}


class OrganizationDirectory:
    """The organizations as the Hub lists them. Names, roles and ids come from the Unity CLI; the short
    name the Editor uses as an organization id ("slug") only from Unity's API, read with the same token."""

    def __init__(self, cli=UnityCli):
        self.cli = cli

    def load(self, user_key, token, primary_org):
        data = self.cli.query(["cloud", "orgs"], timeout=60) or {}
        listed = data.get("organizations") or []
        slugs = self.slugs(user_key, token)
        result = []
        for org in listed:
            key = str(org.get("genesisId", ""))
            result.append({"name": org.get("name", ""), "role": org.get("role", ""),
                           "org_identifier": org.get("id", ""), "billable_user_fk": int(user_key or 0),
                           "id": slugs.get(key) or key, "foreign_key": key})
        if primary_org and not any(org["id"] == primary_org for org in result) and result:
            log("primary organization not found among the listed ones")
        return result

    @staticmethod
    def slugs(user_key, token):
        request = urllib.request.Request(ORGANIZATIONS_API.format(user_key),
                                         headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                results = json.load(reply).get("results") or []
        except (OSError, ValueError) as error:
            log(f"organization names unavailable: {type(error).__name__}")
            return {}
        return {str(org.get("id")): ((org.get("extendedProperties") or {}).get("SLUG") or {}).get("slug", "")
                for org in results}


class AccountSource:
    """Reads the account from the Unity CLI and keeps the last good snapshot."""

    def __init__(self, cli=UnityCli, organizations=None):
        self.cli = cli
        self.organizations = organizations or OrganizationDirectory(cli)
        self.lock = threading.Lock()
        self.ready = threading.Event()               # user and token known
        self.organizations_ready = threading.Event()  # their organizations too (a few seconds later)
        self.current = Account()
        self.loaded_at = 0.0
        self.given_up = None   # the token whose renewal failed: it is not retried by itself

    def active_user(self):
        """The signed-in account from `auth accounts` (it never renews the token, so it never asks for a
        password); {} when nobody is signed in, None when the CLI could not be read."""
        accounts = self.cli.query(["auth", "accounts"], timeout=60)
        if accounts is None:
            return None
        active = accounts.get("activeForeignKey")
        return next((a for a in accounts.get("accounts") or [] if a.get("foreignKey") == active), {})

    def load(self):
        """The user and the token, or None when they could not be read (no answer in time, the password
        prompt cancelled): a failure is not a sign-out. Organizations are read separately, they are slow."""
        user = self.active_user()
        if user is None:
            return None
        if not user:
            return Account()
        info = self.cli.token_info(timeout=TOKEN_WAIT)
        if not info:
            return None
        return Account(user, info["accessToken"], self.expiry_ms(info.get("expiresAt")))

    @staticmethod
    def expiry_ms(text):
        try:
            return int(datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp() * 1000)
        except ValueError:
            return int((time.time() + 3600) * 1000)

    def refresh(self):
        """Reload; True when what the Editor sees has changed. On a failure the last snapshot stays."""
        fresh = self.load()
        if fresh is None:
            with self.lock:
                self.loaded_at, self.given_up = time.time(), self.current.token
            self.ready.set()
            self.organizations_ready.set()
            log("the account could not be read; keeping the last one, no automatic retry for this token")
            return False
        with self.lock:
            before = self.current
            if fresh.user.get("foreignKey") == before.user.get("foreignKey"):
                fresh.organizations = before.organizations
            self.current, self.loaded_at, self.given_up = fresh, time.time(), None
        self.ready.set()
        organizations = (self.organizations.load(fresh.user.get("foreignKey"), fresh.token,
                                                 fresh.user.get("primaryOrg")) if fresh.signed_in else [])
        with self.lock:
            fresh.organizations = organizations
        self.organizations_ready.set()
        return (before.token, before.user, before.organizations) != (fresh.token, fresh.user, organizations)

    def snapshot(self, wait=90, organizations=False):
        (self.organizations_ready if organizations else self.ready).wait(wait)
        with self.lock:
            return self.current

    def due(self):
        """Whether to reload now. Only a renewal may ask for a password, and it is tried once per token;
        the periodic check reads `auth accounts` alone and reloads only when the account itself changed."""
        if not self.ready.is_set():
            return False
        account = self.snapshot(0)
        if account.signed_in and account.expires_in() < RENEW_BEFORE:
            return account.token != self.given_up
        if time.time() - self.loaded_at < RELOAD_EVERY:
            return False
        self.loaded_at = time.time()
        user = self.active_user()
        return user is not None and user.get("foreignKey") != account.user.get("foreignKey")


class EditorConnection:
    """One connected Editor: reads its requests, answers them, receives pushed changes."""

    def __init__(self, sock, service):
        self.sock = sock
        self.service = service
        self.send_lock = threading.Lock()

    def send(self, message):
        frame = json.dumps(message, separators=(",", ":")).encode() + SEPARATOR
        with self.send_lock:
            self.sock.sendall(frame)

    def run(self):
        buffer = b""
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_FRAME:
                    log("dropping an Editor whose message exceeded the size limit")
                    break
                *frames, buffer = buffer.split(SEPARATOR)
                for frame in frames:
                    if frame.strip():
                        self.handle(frame)
        except OSError:
            pass
        finally:
            self.service.forget(self)
            self.sock.close()

    def handle(self, frame):
        try:
            message = json.loads(frame)
            kind = message["type"]
        except (ValueError, KeyError, TypeError):
            log("unreadable message from an Editor")
            return
        for reply in self.service.answer(kind, message.get("data")):
            self.send(reply)


class HubIpcService:
    """Owns the socket, the connected Editors and the account they are told about."""

    def __init__(self, path=SOCKET, source=None):
        self.path = Path(path)
        self.source = source or AccountSource()
        self.clients = []
        self.clients_lock = threading.Lock()
        self.last_client = time.time()

    # ---- what the Editor is told ------------------------------------------------------------------

    def answer(self, kind, data):
        if kind == "config:get":
            return [{"type": "config:get", "data": PRODUCTION}]
        if kind == "connectInfo:get":
            return [self.message("connectInfo", self.source.snapshot())]
        if kind == "userInfo:get":
            return [self.message("userInfo", self.source.snapshot())]
        if kind == "orgInfo:get":
            return [self.message("orgInfo", self.source.snapshot(organizations=True))]
        if kind == "auth:logout":
            threading.Thread(target=self.sign_out, daemon=True).start()
            return []
        if kind == "window:show:modal":
            threading.Thread(target=self.sign_in, daemon=True).start()
            return []
        if kind == "health:check":
            return [{"type": "health:check", "data": {}}]
        # project:open-in-editor-url (the Hub adds the project to its list), window:hide: nothing to do here.
        log(f"ignored {kind}")
        return []

    @staticmethod
    def message(topic, account):
        data = {"connectInfo": account.connect_info, "userInfo": account.user_info,
                "orgInfo": lambda: account.organizations}[topic]()
        return {"type": f"{topic}:changed", "data": data}

    def push(self):
        account = self.source.snapshot(0)
        messages = [self.message(topic, account) for topic in ("connectInfo", "userInfo", "orgInfo")]
        with self.clients_lock:
            clients = list(self.clients)
        for client in clients:
            try:
                for message in messages:
                    client.send(message)
            except OSError:
                pass
        log(f"account pushed to {len(clients)} Editor(s), signed in: {account.signed_in}")

    def sign_in(self):
        """The Editor's Sign in button: the Unity CLI signs in through the browser, then every Editor hears."""
        if self.source.snapshot().signed_in:
            return
        UnityCli.query(["auth", "login"], timeout=600, interactive=True)
        if self.source.refresh():
            self.push()

    def sign_out(self):
        UnityCli.query(["auth", "logout", "--yes"], timeout=60)
        if self.source.refresh():
            self.push()

    # ---- connections ------------------------------------------------------------------------------

    def forget(self, client):
        with self.clients_lock:
            if client in self.clients:
                self.clients.remove(client)
            self.last_client = time.time()

    @staticmethod
    def same_user(sock):
        """The token must not reach another user's process: /tmp is shared."""
        try:
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        except OSError:
            return False
        return struct.unpack("3i", creds)[1] == os.getuid()

    def bind(self):
        """The listening socket, or None when someone (Unity Hub, another copy) already answers there."""
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(str(self.path))
            return None
        except OSError:
            pass
        finally:
            probe.close()
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        old_mask = os.umask(0o177)
        try:
            server.bind(str(self.path))
        finally:
            os.umask(old_mask)
        server.listen()
        return server

    def watch(self, server):
        while True:
            time.sleep(RECHECK)
            with self.clients_lock:
                idle = not self.clients and time.time() - self.last_client > IDLE_EXIT
            if idle:
                log("no Editor connected for a while; exiting")
                self.close(server)
                os._exit(0)
            with self.clients_lock:
                editors = bool(self.clients)
            if editors and self.source.due() and self.source.refresh():
                self.push()

    def close(self, server):
        server.close()
        try:
            self.path.unlink()
        except OSError:
            pass

    def serve(self):
        server = self.bind()
        if server is None:
            log("the socket is already served; nothing to do")
            return 0
        log(f"listening on {self.path}")
        threading.Thread(target=self.source.refresh, daemon=True).start()
        threading.Thread(target=self.watch, args=(server,), daemon=True).start()
        try:
            while True:
                sock, _ = server.accept()
                if not self.same_user(sock):
                    log("refused an Editor of another user")
                    sock.close()
                    continue
                client = EditorConnection(sock, self)
                with self.clients_lock:
                    self.clients.append(client)
                threading.Thread(target=client.run, daemon=True).start()
        except KeyboardInterrupt:
            pass
        finally:
            self.close(server)
        return 0


if __name__ == "__main__":
    sys.exit(HubIpcService().serve())
