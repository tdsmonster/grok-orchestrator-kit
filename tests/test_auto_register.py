#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline regression tests for scripts/auto_register_and_import.py
=============================================================================
Pure stdlib (unittest + unittest.mock) — no network, no services required.
纯标准库离线回归测试：不联网、不依赖任何服务。

Run / 运行:
    python3 -m unittest discover -s tests -v
    # or / 或
    python3 tests/test_auto_register.py
=============================================================================
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "auto_register_and_import.py"

_spec = importlib.util.spec_from_file_location("auto_register_and_import", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def make_args(*extra):
    """Build a real argparse Namespace via the shipped CLI definition."""
    return mod.build_parser().parse_args(list(extra))


def write_account(path: Path, name: str, *, access="at", refresh="rt"):
    payload = {
        "type": "sub2api-data",
        "version": 1,
        "accounts": [
            {
                "name": name,
                "platform": "grok",
                "type": "oauth",
                "credentials": {
                    "access_token": access or "",
                    "refresh_token": refresh or "",
                    "email": name,
                },
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class FakeNova:
    """Minimal NovaApi stand-in that records imports."""

    def __init__(self, existing=()):
        self.existing = {n.lower() for n in existing}
        self.created = []

    def account_exists(self, name):
        return name.lower() in self.existing

    def create_account(self, payload):
        self.created.append(payload)
        self.existing.add(payload["name"].lower())
        return {"id": len(self.created), "name": payload["name"]}


# ---------------------------------------------------------------------------
# 1. Batch payload shape (the original "settings" wrapper bug)
# ---------------------------------------------------------------------------


class TestRegisterPayload(unittest.TestCase):
    def test_register_body_is_flat_settings(self):
        """
        POST /api/register must receive Settings fields at the TOP level.
        A nested {"settings": {...}} was silently ignored by the server, so
        --count was always downgraded to the server default (1).
        """
        captured = {}

        def fake_request(self, url, method="GET", payload=None, headers=None, **kw):
            captured["url"] = url
            captured["payload"] = payload
            return 200, {"batch_id": "batch_x", "count": 5}

        with mock.patch.object(mod.ApiClient, "request", fake_request):
            client = mod.ProGrok("http://127.0.0.1:3080", mod.ApiClient())
            client.start_batch({"count": 5, "concurrency": 2})

        self.assertEqual(captured["payload"]["count"], 5)
        self.assertNotIn("settings", captured["payload"])

    def test_missing_batch_id_raises(self):
        def fake_request(self, url, method="GET", payload=None, headers=None, **kw):
            return 200, {"ok": True}

        with mock.patch.object(mod.ApiClient, "request", fake_request):
            client = mod.ProGrok("http://127.0.0.1:3080", mod.ApiClient())
            with self.assertRaises(mod.ApiError):
                client.start_batch({"count": 1})


class TestSettingsMerge(unittest.TestCase):
    def test_overrides_keep_base_config(self):
        base = {"mail_provider": "custom", "mail_api_key": "secret", "count": 1}
        args = make_args("--count", "5", "--concurrency", "3")
        merged = mod.build_settings(args, base)
        self.assertEqual(merged["count"], 5)
        self.assertEqual(merged["concurrency"], 3)
        self.assertEqual(merged["mail_provider"], "custom")  # preserved / 未被覆盖
        self.assertEqual(merged["mail_api_key"], "secret")
        self.assertFalse(merged["auto_import_enabled"])
        self.assertEqual(merged["registration_json_format"], "sub2api")


# ---------------------------------------------------------------------------
# 2. HTTP error handling (bodies must be surfaced, not swallowed)
# ---------------------------------------------------------------------------


class TestHttpErrors(unittest.TestCase):
    def _http_error(self, code, body):
        return urllib.error.HTTPError(
            "http://x/api", code, "Err", {}, io.BytesIO(body)
        )

    def test_error_body_included_in_message(self):
        err = self._http_error(401, b'{"detail":"invalid credentials"}')
        with mock.patch("urllib.request.urlopen", side_effect=err):
            client = mod.ApiClient(retries=0)
            with self.assertRaises(mod.ApiError) as ctx:
                client.get("http://x/api")
        msg = str(ctx.exception)
        self.assertIn("401", msg)
        self.assertIn("invalid credentials", msg)

    def test_retry_then_success(self):
        calls = {"n": 0}

        class FakeResp:
            def __init__(self, body):
                self._body = body

            def read(self):
                return self._body

            def getcode(self):
                return 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                raise self._http_error(503, b"busy")
            return FakeResp(b'{"ok":true}')

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            with mock.patch("time.sleep", lambda *_: None):
                client = mod.ApiClient(retries=2)
                self.assertEqual(client.get("http://x/api"), {"ok": True})
        self.assertEqual(calls["n"], 2)

    def test_tolerated_status_not_raised(self):
        err = self._http_error(404, b'{"detail":"no accounts"}')
        with mock.patch("urllib.request.urlopen", side_effect=err):
            client = mod.ProGrok("http://p", mod.ApiClient(retries=0))
            self.assertIsNone(client.export_batch("batch_y"))


# ---------------------------------------------------------------------------
# 3. Credential parsing / scoping
# ---------------------------------------------------------------------------


class TestAccountParsing(unittest.TestCase):
    def test_reject_incomplete_credentials(self):
        self.assertIsNone(mod.normalize_account({"name": "a@b.c", "credentials": {"access_token": "x"}}))
        self.assertIsNone(mod.normalize_account({"credentials": {"access_token": "x", "refresh_token": "y"}}))
        self.assertIsNone(mod.normalize_account({"name": "a@b.c", "credentials": "nope"}))
        ok = mod.normalize_account({"name": "a@b.c", "credentials": {"access_token": "x", "refresh_token": "y"}})
        self.assertEqual(ok["name"], "a@b.c")

    def test_envelope_and_flat_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_account(d / "sub2api-a@b.c.json", "a@b.c")
            (d / "sub2api-flat.json").write_text(
                json.dumps({"name": "f@b.c", "credentials": {"access_token": "x", "refresh_token": "y"}}),
                encoding="utf-8",
            )
            (d / "sub2api-broken.json").write_text("{not json", encoding="utf-8")
            names = {a["name"] for a in mod.scan_accounts_dir(d, since_ts=None, lookback=0)}
        self.assertEqual(names, {"a@b.c", "f@b.c"})

    def test_mtime_scoping_excludes_history(self):
        """Only files written around the batch start may be imported."""
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            old = d / "sub2api-old@b.c.json"
            new = d / "sub2api-new@b.c.json"
            write_account(old, "old@b.c")
            write_account(new, "new@b.c")
            past = time.time() - 86400
            os.utime(old, (past, past))

            scoped = mod.scan_accounts_dir(d, since_ts=time.time(), lookback=60)
            everything = mod.scan_accounts_dir(d, since_ts=None, lookback=0)
        self.assertEqual([a["name"] for a in scoped], ["new@b.c"])
        self.assertEqual(len(everything), 2)

    def test_dedupe_within_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            write_account(d / "sub2api-1.json", "dup@b.c")
            write_account(d / "sub2api-2.json", "DUP@b.c")
            found = mod.scan_accounts_dir(d, since_ts=None, lookback=0)
        self.assertEqual(len(found), 1)


# ---------------------------------------------------------------------------
# 4. Pool de-duplication (NovaApi allows duplicate names!)
# ---------------------------------------------------------------------------


class TestPoolDedupe(unittest.TestCase):
    def test_exact_match_required(self):
        """A substring search hit must NOT be treated as the same account."""

        def fake_request(self, url, method="GET", payload=None, headers=None, **kw):
            return 200, {
                "code": 0,
                "data": {"items": [{"id": 1, "name": "someone+1@outlook.com"}]},
            }

        with mock.patch.object(mod.ApiClient, "request", fake_request):
            nova = mod.NovaApi("http://127.0.0.1:8000", mod.ApiClient())
            nova.set_api_key("k")
            self.assertFalse(nova.account_exists("someone@outlook.com"))
            self.assertTrue(nova.account_exists("someone+1@outlook.com"))

    def test_importer_skips_existing(self):
        args = make_args()
        nova = FakeNova(existing=["a@b.c"])
        importer = mod.Importer(nova, args, 2)
        creds = {"access_token": "x", "refresh_token": "y"}
        importer.run(
            [
                {"name": "a@b.c", "credentials": creds},
                {"name": "b@b.c", "credentials": creds},
            ]
        )
        self.assertEqual([p["name"] for p in nova.created], ["b@b.c"])
        self.assertEqual(importer.total, 1)
        self.assertEqual(importer.skipped, ["a@b.c"])

    def test_importer_does_not_reimport_same_pass(self):
        args = make_args()
        nova = FakeNova()
        importer = mod.Importer(nova, args, 2)
        creds = {"access_token": "x", "refresh_token": "y"}
        batch = [{"name": "c@b.c", "credentials": creds}]
        importer.run(batch)
        importer.run(batch)  # second poll pass / 第二轮轮询
        self.assertEqual(len(nova.created), 1)

    def test_failed_import_does_not_abort_batch(self):
        args = make_args()

        class Boom(FakeNova):
            def create_account(self, payload):
                if payload["name"] == "bad@b.c":
                    raise mod.ApiError("boom", status=400)
                return super().create_account(payload)

        nova = Boom()
        importer = mod.Importer(nova, args, None)
        creds = {"access_token": "x", "refresh_token": "y"}
        importer.run(
            [
                {"name": "bad@b.c", "credentials": creds},
                {"name": "good@b.c", "credentials": creds},
            ]
        )
        self.assertEqual([p["name"] for p in nova.created], ["good@b.c"])
        self.assertIn("bad@b.c", importer.failed)


# ---------------------------------------------------------------------------
# 5. Polling loop: terminal states, stall detection, exit codes
# ---------------------------------------------------------------------------


def _patch_pipeline(state_iter, *, exported=None):
    """Patch ProGrok/NovaApi surfaces used by run_pipeline."""
    states = list(state_iter)

    def get_batch(self, batch_id):
        return states.pop(0) if len(states) > 1 else states[0]

    return [
        mock.patch.object(mod.ProGrok, "health", lambda self: {"ok": True}),
        mock.patch.object(mod.ProGrok, "get_config", lambda self: {"mail_provider": "custom"}),
        mock.patch.object(mod.ProGrok, "output_paths", lambda self: {"accounts": "/tmp"}),
        mock.patch.object(
            mod.ProGrok, "start_batch", lambda self, s, paused=False: {"batch_id": "b1", "count": s["count"]}
        ),
        mock.patch.object(mod.ProGrok, "get_batch", get_batch),
        mock.patch.object(mod.ProGrok, "export_batch", lambda self, bid: exported),
        mock.patch.object(mod.NovaApi, "login", lambda self, e, p: "tok"),
        mock.patch.object(mod, "preflight", lambda *a, **k: []),
        mock.patch.object(mod, "scan_accounts_dir", lambda *a, **k: []),
        mock.patch.dict(os.environ, {"NOVAAPI_ADMIN_EMAIL": "a@b.c", "NOVAAPI_ADMIN_PASSWORD": "pw"}),
    ]


class TestPollingLoop(unittest.TestCase):
    def _run(self, states, *extra):
        args = make_args(
            "--count", "1",
            "--poll-interval", "0.01",
            "--stall-timeout", "0.2",
            "--max-wait", "30",
            "--skip-preflight",
            *extra,
        )
        patches = _patch_pipeline(states)
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        with mock.patch("time.sleep", lambda *_: None):
            return mod.run_pipeline(args)

    def test_terminal_status_exits_ok(self):
        code = self._run([{"status": "done", "count": 1, "finished": 1, "ok_count": 1}])
        self.assertEqual(code, mod.EXIT_OK)

    def test_stopping_is_terminal(self):
        """'stopping' used to loop forever because it was not in the terminal set."""
        code = self._run([{"status": "stopping", "count": 1, "finished": 0, "ok_count": 0}])
        self.assertEqual(code, mod.EXIT_OK)

    def test_stall_detection_aborts(self):
        start = time.time()
        code = self._run([{"status": "running", "count": 1, "finished": 0, "ok_count": 0}])
        self.assertEqual(code, mod.EXIT_STALLED)
        self.assertLess(time.time() - start, 10)

    def test_finished_but_status_running_terminates(self):
        code = self._run([{"status": "running", "count": 1, "finished": 1, "ok_count": 1}])
        self.assertEqual(code, mod.EXIT_OK)


# ---------------------------------------------------------------------------
# 6. Redaction
# ---------------------------------------------------------------------------


class TestRedaction(unittest.TestCase):
    def test_secrets_masked(self):
        out = mod.dumps_redacted(
            {
                "count": 5,
                "mail_provider": "custom",
                "mail_api_key": "user:password",
                "nested": {"admin_password": "hunter2", "token": "abc"},
            }
        )
        self.assertIn('"count": 5', out)
        self.assertNotIn("hunter2", out)
        self.assertNotIn("user:password", out)
        self.assertNotIn('"abc"', out)

    def test_env_file_does_not_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text("NOVAAPI_ADMIN_EMAIL=fromfile\nNEW_KEY_FOR_TEST=yes\n", encoding="utf-8")
            os.environ.pop("NEW_KEY_FOR_TEST", None)
            os.environ["NOVAAPI_ADMIN_EMAIL"] = "fromenv"
            try:
                loaded = mod.load_env_file(env)
                self.assertGreaterEqual(loaded, 1)
                self.assertEqual(os.environ["NOVAAPI_ADMIN_EMAIL"], "fromenv")
                self.assertEqual(os.environ["NEW_KEY_FOR_TEST"], "yes")
            finally:
                os.environ.pop("NEW_KEY_FOR_TEST", None)


# ---------------------------------------------------------------------------
# 7. CLI surface
# ---------------------------------------------------------------------------


class TestCli(unittest.TestCase):
    def test_count_validation(self):
        with self.assertRaises(SystemExit):
            make_args("--count", "0")
        with self.assertRaises(SystemExit):
            make_args("--count", "abc")

    def test_dry_run_payload_has_requested_count(self):
        args = make_args("--count", "5", "--dry-run")
        settings = mod.build_settings(args, {})
        self.assertEqual(settings["count"], 5)
        self.assertLessEqual(settings["concurrency"], 8)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as ctx:
            make_args("--version")
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
