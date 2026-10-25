#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_register_and_import.py
=============================================================================
Grok batch registration + Sub2API (NovaApi) pool import pipeline.
Grok 批量注册 + Sub2API 账号池原子导入流水线。
=============================================================================
Pipeline / 流水线:
  1. ProGrok  (default :3080)  -> POST /api/register  (batch creation / 下发批次)
  2. ProGrok                   -> GET  /api/batches/{id} (live progress / 进度轮询)
  3. ProGrok                   -> GET  /api/download?format=sub2api_json&batch_id=...
                                  (batch-scoped export / 仅导出本批次账号)
  4. NovaApi  (default :8000)  -> POST /api/v1/admin/accounts (pool import / 入库)

Requirements / 依赖:
  Python 3.8+ and the standard library ONLY. No pip install required.
  仅需 Python 3.8+ 标准库，无需安装任何第三方包。

Usage / 用法:
  python3 scripts/auto_register_and_import.py --count 5
  python3 scripts/auto_register_and_import.py --count 5 --dry-run
  python3 scripts/auto_register_and_import.py --import-existing   # backfill / 补齐历史账号
  python3 scripts/auto_register_and_import.py --help

Env vars / 环境变量 (all optional, CLI flags win / 均为可选，命令行优先):
  PROGROK_API_URL, NOVAAPI_URL, NOVAAPI_ADMIN_EMAIL, NOVAAPI_ADMIN_PASSWORD,
  NOVAAPI_API_KEY, HOTMAIL_HELPER_URL, SOLVER_URL, GROK_ACCOUNTS_DIR

Exit codes / 退出码:
  0 = success            1 = runtime/config error       2 = usage error
  3 = partial success    4 = stalled / timed out        130 = interrupted
=============================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

__version__ = "1.1.0"

# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_PARTIAL = 3
EXIT_STALLED = 4
EXIT_INTERRUPTED = 130

DEFAULT_PROGROK_URL = "http://127.0.0.1:3080"
DEFAULT_NOVAAPI_URL = "http://127.0.0.1:8000"
DEFAULT_HOTMAIL_URL = "http://127.0.0.1:17373"
DEFAULT_SOLVER_URL = "http://127.0.0.1:5072"

# Batch statuses that mean "no further progress will happen".
# 批次终态：出现即停止轮询（"stopping" 也算终态，避免 Ctrl-C / stop 后无限等待）。
TERMINAL_STATUSES = frozenset(
    {"done", "partial", "failed", "stopped", "stopping", "cancelled", "canceled", "error"}
)

RETRY_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

SECRET_KEY_HINTS = (
    "password", "passwd", "token", "secret", "api_key", "apikey",
    "authorization", "cookie", "key",
)

USER_AGENT = f"grok-orchestrator-kit/{__version__} (+https://github.com/tdsmonster/grok-orchestrator-kit)"


# ---------------------------------------------------------------------------
# Logging / 日志
# ---------------------------------------------------------------------------

_VERBOSE = False


def log(msg: str, *, level: str = "INFO") -> None:
    """Timestamped stdout log line. / 带时间戳的标准输出日志。"""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {msg}", flush=True)


def vlog(msg: str) -> None:
    if _VERBOSE:
        log(msg, level="DEBUG")


def warn(msg: str) -> None:
    log(f"⚠️  {msg}")


def fail(msg: str) -> None:
    log(f"❌ {msg}")


# ---------------------------------------------------------------------------
# Small helpers / 辅助函数
# ---------------------------------------------------------------------------


class ApiError(RuntimeError):
    """HTTP/API failure with a readable, redacted message. / 可读的接口异常。"""

    def __init__(self, message: str, *, status: Optional[int] = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


def redact(value: Any) -> Any:
    """Recursively mask secrets before printing. / 打印前递归脱敏。"""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if any(h in str(k).lower() for h in SECRET_KEY_HINTS):
                out[k] = "***" if v in (None, "") else f"***<{len(str(v))} chars>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def dumps_redacted(obj: Any) -> str:
    return json.dumps(redact(obj), ensure_ascii=False, indent=2, sort_keys=True)


def load_env_file(path: Path) -> int:
    """
    Minimal .env loader (KEY=VALUE, # comments). Never overrides real env vars.
    极简 .env 解析，不覆盖已存在的真实环境变量。返回载入的键数量。
    """
    if not path.is_file():
        return 0
    count = 0
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if not key or key in os.environ:
                continue
            os.environ[key] = val
            count += 1
    except OSError as exc:  # pragma: no cover - defensive
        warn(f"无法读取 .env 文件 / cannot read {path}: {exc}")
    return count


def parse_iso_ts(value: str) -> Optional[float]:
    """Parse ISO-8601 timestamps from batch payloads. / 解析 ISO 时间戳。"""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        import datetime as _dt

        return _dt.datetime.fromisoformat(text).timestamp()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# HTTP layer / HTTP 层
# ---------------------------------------------------------------------------


class ApiClient:
    """
    Thin JSON-over-HTTP client with retries and meaningful errors.
    轻量 JSON HTTP 客户端：自动重试 + 可读错误信息（含响应体）。
    """

    def __init__(self, timeout: float = 20.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def request(
        self,
        url: str,
        method: str = "GET",
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        *,
        expect_json: bool = True,
        tolerate_status: Iterable[int] = (),
    ) -> Tuple[int, Any]:
        body = None
        hdrs = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)

        tolerate = set(tolerate_status)
        last_exc: Optional[Exception] = None

        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    status = resp.getcode()
                    if not expect_json:
                        return status, raw.decode("utf-8", "replace")
                    if not raw:
                        return status, {}
                    try:
                        return status, json.loads(raw.decode("utf-8"))
                    except json.JSONDecodeError as exc:
                        raise ApiError(
                            f"{method} {url} 返回了非 JSON 响应 / non-JSON response: "
                            f"{raw[:200]!r}",
                            status=status,
                        ) from exc
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:600]
                except Exception:  # pragma: no cover - body may be unreadable
                    detail = "<unreadable body>"
                if exc.code in tolerate:
                    if expect_json:
                        try:
                            return exc.code, json.loads(detail) if detail else {}
                        except json.JSONDecodeError:
                            return exc.code, {"detail": detail}
                    return exc.code, detail
                if exc.code in RETRY_STATUS and attempt < self.retries:
                    last_exc = exc
                    time.sleep(self._backoff(attempt))
                    continue
                raise ApiError(
                    f"{method} {url} -> HTTP {exc.code} ({exc.reason}); "
                    f"响应体 / body: {detail.strip() or '<empty>'}",
                    status=exc.code,
                    body=detail,
                ) from exc
            except urllib.error.URLError as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self._backoff(attempt))
                    continue
                raise ApiError(
                    f"{method} {url} 连接失败 / connection failed: {exc.reason}",
                ) from exc
            except (TimeoutError, OSError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(self._backoff(attempt))
                    continue
                raise ApiError(f"{method} {url} 请求超时/网络异常: {exc}") from exc

        raise ApiError(f"{method} {url} 重试耗尽 / retries exhausted: {last_exc}")

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(8.0, 0.5 * (2 ** attempt)) + random.uniform(0, 0.3)

    # -- convenience wrappers ------------------------------------------------
    def get(self, url: str, **kw: Any) -> Any:
        return self.request(url, "GET", **kw)[1]

    def post(self, url: str, payload: Any = None, **kw: Any) -> Any:
        return self.request(url, "POST", payload, **kw)[1]

    def delete(self, url: str, **kw: Any) -> Any:
        return self.request(url, "DELETE", **kw)[1]


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


# ---------------------------------------------------------------------------
# ProGrok API / ProGrok 接口
# ---------------------------------------------------------------------------


class ProGrok:
    def __init__(self, base_url: str, client: ApiClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client

    def health(self) -> Dict[str, Any]:
        return self.client.get(join_url(self.base_url, "/api/health"))

    def get_config(self) -> Dict[str, Any]:
        data = self.client.get(join_url(self.base_url, "/api/config"))
        return data if isinstance(data, dict) else {}

    def start_batch(self, settings: Dict[str, Any], *, paused: bool = False) -> Dict[str, Any]:
        """
        POST /api/register expects the Settings object FLAT in the JSON body.
        The previous implementation wrapped it in {"settings": {...}}, which the
        server silently ignored -> every run fell back to count=1 defaults.
        POST /api/register 要求把 Settings 字段平铺在请求体里；嵌套一层会被静默忽略。
        """
        url = join_url(self.base_url, "/api/register")
        if paused:
            url += "?paused=true"
        data = self.client.post(url, settings)
        if not isinstance(data, dict):
            raise ApiError(f"/api/register 返回了异常响应 / unexpected response: {data!r}")
        if data.get("ok") is False or data.get("error"):
            raise ApiError(f"/api/register 拒绝请求 / rejected: {data.get('error') or data}")
        if not str(data.get("batch_id") or data.get("id") or "").strip():
            raise ApiError(
                "批次下发响应缺少 batch_id / /api/register returned no batch_id: "
                f"{dumps_redacted(data)[:400]}"
            )
        return data

    def get_batch(self, batch_id: str) -> Dict[str, Any]:
        url = join_url(self.base_url, f"/api/batches/{urllib.parse.quote(batch_id, safe='')}")
        data = self.client.get(url)
        return data if isinstance(data, dict) else {}

    def stop_batch(self, batch_id: str) -> Dict[str, Any]:
        url = join_url(self.base_url, f"/api/batches/{urllib.parse.quote(batch_id, safe='')}/stop")
        status, data = self.client.request(url, "POST", tolerate_status=(404, 409))
        if status >= 400:
            return {}
        return data if isinstance(data, dict) else {}

    def export_batch(self, batch_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Batch-scoped export; returns None when the endpoint has nothing (404).
        仅导出本批次成功账号；无数据时返回 None。
        """
        query = urllib.parse.urlencode({"format": "sub2api_json", "batch_id": batch_id})
        url = join_url(self.base_url, f"/api/download?{query}")
        status, data = self.client.request(url, "GET", tolerate_status=(404, 400))
        if status >= 400:
            vlog(f"批次导出接口返回 HTTP {status}（尚无成功账号）/ no exportable accounts yet")
            return None
        if isinstance(data, dict) and isinstance(data.get("accounts"), list):
            return [a for a in data["accounts"] if isinstance(a, dict)]
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)]
        return None

    def output_paths(self) -> Dict[str, str]:
        try:
            data = self.client.get(join_url(self.base_url, "/api/output-paths"))
        except ApiError:
            return {}
        items = data.get("items") if isinstance(data, dict) else None
        out: Dict[str, str] = {}
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and it.get("key") and it.get("path"):
                    out[str(it["key"])] = str(it["path"])
        return out


# ---------------------------------------------------------------------------
# NovaApi / Sub2API API
# ---------------------------------------------------------------------------


class NovaApi:
    def __init__(self, base_url: str, client: ApiClient) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self._token: Optional[str] = None
        self._existing_cache: Dict[str, bool] = {}

    # -- auth ---------------------------------------------------------------
    def login(self, email: str, password: str) -> str:
        url = join_url(self.base_url, "/api/v1/auth/login")
        data = self.client.post(url, {"email": email, "password": password})
        token = None
        if isinstance(data, dict):
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            token = payload.get("access_token") or payload.get("token")
        if not token:
            raise ApiError(
                f"NovaApi 登录失败：响应中没有 access_token / login failed: {dumps_redacted(data)[:300]}"
            )
        self._token = str(token)
        return self._token

    def set_api_key(self, api_key: str) -> None:
        self._token = api_key

    def _headers(self) -> Dict[str, str]:
        if not self._token:
            raise ApiError("NovaApi 尚未认证 / not authenticated (call login() first)")
        return {"Authorization": f"Bearer {self._token}"}

    # -- accounts -----------------------------------------------------------
    def account_exists(self, name: str) -> bool:
        """
        Exact-name existence probe. NovaApi silently allows duplicate names, so
        client-side dedupe is mandatory (otherwise every run re-imports history).
        NovaApi 允许同名重复，因此必须客户端去重。
        """
        key = name.strip().lower()
        if key in self._existing_cache:
            return self._existing_cache[key]
        query = urllib.parse.urlencode({"page": 1, "page_size": 20, "search": name})
        url = join_url(self.base_url, f"/api/v1/admin/accounts?{query}")
        try:
            data = self.client.get(url, headers=self._headers())
        except ApiError as exc:
            warn(f"查重失败（将按未存在处理）/ duplicate probe failed for {name}: {exc}")
            self._existing_cache[key] = False
            return False
        items = []
        if isinstance(data, dict):
            payload = data.get("data") if isinstance(data.get("data"), dict) else data
            items = payload.get("items") or payload.get("list") or []
        elif isinstance(data, list):
            items = data
        found = any(
            str(it.get("name", "")).strip().lower() == key
            for it in items
            if isinstance(it, dict)
        )
        self._existing_cache[key] = found
        return found

    def create_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = join_url(self.base_url, "/api/v1/admin/accounts")
        data = self.client.post(url, payload, headers=self._headers())
        if isinstance(data, dict) and data.get("code") not in (None, 0):
            raise ApiError(f"入库被拒绝 / import rejected: {data.get('message') or data}")
        result = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        if not isinstance(result, dict) or not result.get("id"):
            raise ApiError(f"入库响应缺少账号 ID / response has no account id: {dumps_redacted(data)[:300]}")
        return result


# ---------------------------------------------------------------------------
# Account harvesting / 账号采集
# ---------------------------------------------------------------------------


def normalize_account(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Normalize one credential record (unwrap sub2api export envelopes).
    规整单条凭据记录，兼容单账号对象与 sub2api 导出信封。
    """
    if not isinstance(raw, dict):
        return None
    if "accounts" in raw and isinstance(raw["accounts"], list):
        return None  # envelope handled by caller
    creds = raw.get("credentials")
    if not isinstance(creds, dict):
        return None
    name = str(raw.get("name") or creds.get("email") or "").strip()
    access = creds.get("access_token")
    refresh = creds.get("refresh_token")
    if not name or not isinstance(access, str) or not access.strip():
        return None
    if not isinstance(refresh, str) or not refresh.strip():
        return None
    out = dict(raw)
    out["name"] = name
    out["platform"] = raw.get("platform") or "grok"
    out["type"] = raw.get("type") or "oauth"
    out["credentials"] = creds
    return out


def accounts_from_file(path: Path) -> List[Dict[str, Any]]:
    """Read one credential file; tolerate both envelope and flat shapes."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        warn(f"跳过损坏文件 / skipping unreadable file {path.name}: {exc}")
        return []
    rows: List[Dict[str, Any]] = []
    if isinstance(data, dict) and isinstance(data.get("accounts"), list):
        rows = [r for r in data["accounts"] if isinstance(r, dict)]
    elif isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        rows = [data]
    out = []
    for r in rows:
        norm = normalize_account(r)
        if norm:
            out.append(norm)
    return out


def scan_accounts_dir(accounts_dir: Path, *, since_ts: Optional[float], lookback: float) -> List[Dict[str, Any]]:
    """
    Scan credential files written after `since_ts` (minus `lookback` tolerance).
    `since_ts=None` means "all files" (explicit --import-existing backfill).
    仅采集批次开始后写入的凭据文件；since_ts=None 表示全量（显式补齐模式）。
    """
    if not accounts_dir.is_dir():
        warn(f"账号目录不存在 / accounts dir not found: {accounts_dir}")
        return []
    cutoff = None if since_ts is None else since_ts - max(0.0, lookback)
    picked: List[Tuple[float, Path]] = []
    for path in accounts_dir.glob("sub2api-*.json"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if cutoff is not None and mtime < cutoff:
            continue
        picked.append((mtime, path))
    picked.sort(key=lambda item: item[0])

    collected: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for _, path in picked:
        for acct in accounts_from_file(path):
            key = acct["name"].lower()
            if key in seen:
                continue
            seen.add(key)
            collected.append(acct)
    vlog(f"目录扫描命中 {len(picked)} 个文件 / scanned {len(picked)} files -> {len(collected)} accounts")
    return collected


def build_import_payload(acct: Dict[str, Any], args: argparse.Namespace, group_id: Optional[int]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": acct["name"],
        "platform": acct.get("platform") or "grok",
        "type": acct.get("type") or "oauth",
        "credentials": acct["credentials"],
        "concurrency": int(acct.get("concurrency") or args.account_concurrency),
        "priority": int(acct.get("priority") or args.priority),
        "rate_multiplier": float(acct.get("rate_multiplier") or 1.0),
        "auto_pause_on_expired": bool(acct.get("auto_pause_on_expired", True)),
        "status": "active",
    }
    if group_id is not None:
        payload["group_ids"] = [int(group_id)]
    return payload


# ---------------------------------------------------------------------------
# Settings assembly / 批次参数组装
# ---------------------------------------------------------------------------


def build_settings(args: argparse.Namespace, base_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge CLI intent on top of the server's current settings. Sending the whole
    (known-good) settings object avoids clobbering mail-provider credentials that
    the operator already configured. 以服务端现有配置为基底，避免覆盖已配置的收信凭据。
    """
    settings: Dict[str, Any] = dict(base_config)
    settings.update(
        {
            "registration_target": args.target,
            "count": int(args.count),
            "concurrency": int(args.concurrency),
            "stagger_ms": int(args.stagger_ms),
            "probe_model": args.probe_model,
            "pre_import_probe_enabled": not args.skip_probe,
            "auto_import_enabled": False,  # import is handled here / 由本脚本统一入库
            "registration_json_format": "sub2api",
            "grok_headless": not args.headed,
            "hotmail_local_base_url": args.hotmail_url,
            "local_solver_url": args.solver_url,
        }
    )
    if args.mail_provider:
        settings["mail_provider"] = args.mail_provider
    if args.captcha_provider:
        settings["captcha_provider"] = args.captcha_provider
    if args.registration_mode:
        settings["registration_mode"] = args.registration_mode
    return settings


# ---------------------------------------------------------------------------
# Preflight / 启动前自检
# ---------------------------------------------------------------------------


def _probe_reachable(url: str, timeout: float = 8.0) -> Tuple[bool, str]:
    """
    Plain liveness probe: any HTTP answer below 500 counts as "alive".
    Local helper services often serve HTML, so we must not require JSON.
    连通性探测：只要返回 <500 即视为在线（本地助手多为 HTML 页面）。
    """
    client = ApiClient(timeout=timeout, retries=0)
    try:
        status, _ = client.request(url, "GET", expect_json=False, tolerate_status=range(400, 500))
        return True, f"HTTP {status}"
    except ApiError as exc:
        return False, str(exc)


def preflight(progrok: ProGrok, args: argparse.Namespace, settings: Dict[str, Any]) -> List[str]:
    problems: List[str] = []

    try:
        health = progrok.health()
        ok = bool(health.get("ok", True)) if isinstance(health, dict) else True
        version = health.get("version") if isinstance(health, dict) else None
        if ok:
            log(f"✅ ProGrok 在线 / online: {progrok.base_url}" + (f" (v{version})" if version else ""))
        else:
            problems.append(f"ProGrok 健康检查未通过 / health check failed: {health}")
    except ApiError as exc:
        problems.append(
            f"无法连接 ProGrok / cannot reach {progrok.base_url} — 先启动注册引擎 "
            f"(docker compose up -d / 对应进程) 后重试。原始错误: {exc}"
        )

    mx = settings.get("mail_provider")
    if mx == "hotmail_local":
        url = str(settings.get("hotmail_local_base_url") or args.hotmail_url)
        alive, detail = _probe_reachable(url, min(args.request_timeout, 8))
        if alive:
            log(f"✅ Outlook 收信助手在线 / mail helper online: {url} ({detail})")
        else:
            warn(f"收信助手可能未启动 / mail helper unreachable at {url}: {detail}")

    if str(settings.get("captcha_provider") or "") == "local":
        url = str(settings.get("local_solver_url") or args.solver_url)
        alive, detail = _probe_reachable(url, min(args.request_timeout, 8))
        if alive:
            log(f"✅ 本地 Turnstile 求解器在线 / solver online: {url} ({detail})")
        else:
            warn(f"求解器可能未启动 / solver unreachable at {url}: {detail}")

    return problems


# ---------------------------------------------------------------------------
# Import driver / 入库驱动器
# ---------------------------------------------------------------------------


class Importer:
    def __init__(self, nova: NovaApi, args: argparse.Namespace, group_id: Optional[int]) -> None:
        self.nova = nova
        self.args = args
        self.group_id = group_id
        self.imported: List[str] = []
        self.skipped: List[str] = []
        self.failed: Dict[str, str] = {}
        self._attempted: Set[str] = set()
        self._seen: Set[str] = set()

    def run(self, candidates: Iterable[Dict[str, Any]]) -> int:
        """Import new accounts; returns how many were imported this pass. / 返回本轮入库数。"""
        fresh = 0
        for acct in candidates:
            name = acct["name"]
            key = name.lower()
            if key in self._seen:
                continue
            self._seen.add(key)
            if key in self._attempted:
                continue

            if self.nova.account_exists(name):
                vlog(f"已存在，跳过 / already in pool: {name}")
                self.skipped.append(name)
                self._attempted.add(key)
                continue

            payload = build_import_payload(acct, self.args, self.group_id)
            if self.args.dry_run:
                log(f"🧪 [dry-run] 将入库 / would import: {name}")
                self.imported.append(name)
                self._attempted.add(key)
                fresh += 1
                continue

            try:
                result = self.nova.create_account(payload)
            except ApiError as exc:
                # Retry once on transient network/5xx issues before giving up.
                if isinstance(exc.status, int) and exc.status in RETRY_STATUS:
                    time.sleep(2.0)
                    try:
                        result = self.nova.create_account(payload)
                    except ApiError as exc2:
                        self.failed[name] = str(exc2)
                        fail(f"入库失败 / import failed [{name}]: {exc2}")
                        self._attempted.add(key)
                        continue
                else:
                    self.failed[name] = str(exc)
                    fail(f"入库失败 / import failed [{name}]: {exc}")
                    self._attempted.add(key)
                    continue
            except Exception as exc:  # defensive: never kill the whole batch
                self.failed[name] = repr(exc)
                fail(f"入库异常 / import error [{name}]: {exc!r}")
                self._attempted.add(key)
                continue

            self.imported.append(name)
            self._attempted.add(key)
            fresh += 1
            log(
                f"✅ 账号入库成功 / imported [{name}] id={result.get('id')} "
                f"group={self.group_id if self.group_id is not None else '-'}"
            )
        return fresh

    @property
    def total(self) -> int:
        return len(self.imported)


# ---------------------------------------------------------------------------
# Main pipeline / 主流水线
# ---------------------------------------------------------------------------


def run_pipeline(args: argparse.Namespace) -> int:
    client = ApiClient(timeout=args.request_timeout, retries=args.retries)
    progrok = ProGrok(args.progrok_url, client)

    # ---- resolve settings -------------------------------------------------
    try:
        base_config = progrok.get_config()
        vlog(f"已读取服务端配置 / loaded server settings ({len(base_config)} keys)")
    except ApiError as exc:
        warn(f"无法读取 ProGrok 配置，使用内置默认值 / cannot read /api/config: {exc}")
        base_config = {}

    settings = build_settings(args, base_config)

    accounts_dir = Path(args.accounts_dir).expanduser() if args.accounts_dir else None
    if accounts_dir is None:
        paths = progrok.output_paths()
        if paths.get("accounts"):
            accounts_dir = Path(paths["accounts"]).expanduser()
            vlog(f"账号目录来自 ProGrok / accounts dir from /api/output-paths: {accounts_dir}")
        else:
            accounts_dir = Path.home() / "services/progrok/runtime/data/accounts"
            warn(f"回退到默认账号目录 / falling back to {accounts_dir}")

    # ---- NovaApi credential resolution -----------------------------------
    nova_url = args.novaapi_url or base_config.get("sub2api_base_url") or DEFAULT_NOVAAPI_URL
    admin_email = (
        args.admin_email
        or os.getenv("NOVAAPI_ADMIN_EMAIL")
        or (base_config.get("sub2api_admin_email") or "").strip()
    )
    admin_password = (
        args.admin_password
        or os.getenv("NOVAAPI_ADMIN_PASSWORD")
        or (base_config.get("sub2api_admin_password") or "").strip()
    )
    api_key = (args.api_key or os.getenv("NOVAAPI_API_KEY") or (base_config.get("sub2api_api_key") or "")).strip()
    auth_mode = (args.auth_mode or base_config.get("sub2api_auth_mode") or "password").strip()

    group_id_raw = args.group_id if args.group_id is not None else base_config.get("sub2api_group_id")
    group_id: Optional[int]
    try:
        group_id = int(group_id_raw) if str(group_id_raw).strip() not in ("", "None", "0") else None
    except (TypeError, ValueError):
        group_id = 2

    nova = NovaApi(nova_url, client)

    if not args.dry_run:
        if auth_mode == "api_key" and api_key:
            nova.set_api_key(api_key)
            log(f"✅ NovaApi 使用 API Key 认证 / using api key against {nova_url}")
        else:
            if not (admin_email and admin_password):
                fail(
                    "缺少 NovaApi 管理员凭据 / missing NovaApi credentials. 请通过以下任一方式提供：\n"
                    "  export NOVAAPI_ADMIN_EMAIL=admin@example.com\n"
                    "  export NOVAAPI_ADMIN_PASSWORD='***'\n"
                    "  python3 scripts/auto_register_and_import.py --admin-email ... --admin-password ...\n"
                    "  (或在 ProGrok /api/config 中设置 sub2api_admin_email / sub2api_admin_password)"
                )
                return EXIT_ERROR
            try:
                nova.login(admin_email, admin_password)
                log(f"✅ NovaApi 登录成功 / logged in as {admin_email} @ {nova_url}")
            except ApiError as exc:
                fail(f"NovaApi 登录失败 / login failed: {exc}")
                return EXIT_ERROR

    # ---- preflight --------------------------------------------------------
    if not args.skip_preflight:
        problems = preflight(progrok, args, settings)
        if problems:
            for p in problems:
                fail(p)
            return EXIT_ERROR

    importer = Importer(nova, args, group_id)

    # ---- backfill mode ----------------------------------------------------
    if args.import_existing:
        log(f"📦 补齐模式：扫描 {accounts_dir} 中的全部历史凭据 / backfill mode")
        candidates = scan_accounts_dir(accounts_dir, since_ts=None, lookback=0)
        log(f"🔎 发现 {len(candidates)} 个候选账号 / candidates found")
        importer.run(candidates)
        summary("backfill", None, importer, args, group_id)
        return _exit_code(args, importer, stalled=False)

    if args.dry_run:
        log("🧪 dry-run：以下为本批将下发的 settings（已脱敏）/ settings payload (redacted):")
        print(dumps_redacted(settings))
        log(f"🧪 dry-run：账号目录为 / accounts dir: {accounts_dir}")
        return EXIT_OK

    # ---- start batch ------------------------------------------------------
    log(
        f"🚀 下发注册批次 / starting batch: count={args.count} concurrency={args.concurrency} "
        f"stagger={args.stagger_ms}ms target={settings.get('registration_target')} "
        f"mail={settings.get('mail_provider')}"
    )
    started_at = time.time()
    try:
        batch = progrok.start_batch(settings)
    except ApiError as exc:
        fail(f"批次下发失败 / failed to start batch: {exc}")
        return EXIT_ERROR

    batch_id = str(batch.get("batch_id") or batch.get("id") or "").strip()
    if not batch_id:
        fail(f"批次下发响应缺少 batch_id / response missing batch_id: {dumps_redacted(batch)[:400]}")
        return EXIT_ERROR

    server_count = batch.get("count")
    log(f"📡 批次已创建 / batch created: {batch_id} (server count={server_count})")
    if server_count is not None and int(server_count) != int(args.count):
        warn(
            f"服务端接受的 count={server_count} 与请求的 {args.count} 不一致 / "
            f"server accepted count={server_count}, requested {args.count}"
        )

    # ---- poll + import ----------------------------------------------------
    last_snapshot: Optional[Tuple[Any, ...]] = None
    last_change = time.time()
    stalled = False
    grace_left = 3
    status = ""
    finished = ok_count = 0
    total = int(server_count or args.count)

    while True:
        try:
            state = progrok.get_batch(batch_id)
        except ApiError as exc:
            warn(f"进度查询失败（稍后重试）/ poll failed: {exc}")
            state = {}

        if state:
            status = str(state.get("status") or "").lower()
            total = int(state.get("count") or total or 0)
            finished = int(state.get("finished") or 0)
            ok_count = int(state.get("ok_count") or 0)
            snapshot = (
                status, finished, total, ok_count,
                int(state.get("fail_count") or 0),
                int(state.get("spawned") or 0),
            )
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                last_change = time.time()

        # Import whatever is already on disk / 增量入库
        candidates = scan_accounts_dir(accounts_dir, since_ts=started_at, lookback=args.mtime_tolerance)
        exported = progrok.export_batch(batch_id)
        if exported:
            candidates = exported + candidates  # batch export first (authoritative)

        fresh = importer.run(candidates)
        log(
            f"📊 进度 / progress: {finished}/{total or '?'} ok={ok_count} "
            f"status={status or '?'} 已入库/imported={importer.total}"
            + (f" (+{fresh})" if fresh else "")
        )

        if status in TERMINAL_STATUSES:
            break

        if total and finished >= total:
            # Backend counters can reach the target a poll or two before the
            # batch flips to a terminal status; allow a bounded grace window so
            # we never spin forever on status="running".
            # 计数已达标但状态仍为 running 时，最多再等 3 轮。
            if status in ("running", "paused", "stopping"):
                grace_left -= 1
                if grace_left <= 0:
                    vlog("计数已达标，状态未翻转，结束轮询 / counters complete, ending poll")
                    break
                time.sleep(min(max(args.poll_interval, 1.0), 3.0))
                continue
            break

        idle = time.time() - last_change
        if idle >= args.stall_timeout:
            warn(
                f"批次 {batch_id} 已 {int(idle)}s 无进度（阈值 {args.stall_timeout}s）/ "
                f"no progress for {int(idle)}s — aborting polling"
            )
            stalled = True
            break
        if args.max_wait and (time.time() - started_at) >= args.max_wait:
            warn(f"达到最大等待时间 {args.max_wait}s / max wait reached — aborting polling")
            stalled = True
            break

        time.sleep(max(1.0, args.poll_interval))

    # ---- final drain ------------------------------------------------------
    try:
        final_candidates = scan_accounts_dir(accounts_dir, since_ts=started_at, lookback=args.mtime_tolerance)
        exported = progrok.export_batch(batch_id)
        if exported:
            final_candidates = exported + final_candidates
        importer.run(final_candidates)
    except Exception as exc:  # pragma: no cover - defensive
        warn(f"收尾入库异常 / final import pass failed: {exc!r}")

    summary(batch_id, status, importer, args, group_id, finished=finished, total=total, ok_count=ok_count)
    return _exit_code(args, importer, stalled=stalled)


def summary(
    batch_id: Optional[str],
    status: Optional[str],
    importer: Importer,
    args: argparse.Namespace,
    group_id: Optional[int],
    *,
    finished: int = 0,
    total: int = 0,
    ok_count: int = 0,
) -> None:
    log("─" * 62)
    log("📋 执行摘要 / summary")
    log(f"   批次 batch      : {batch_id or '-'}  (status={status or '-'})")
    if total:
        log(f"   生产 produced   : {ok_count}/{finished} ok (target {total})")
    log(f"   入库 imported   : {importer.total}")
    log(f"   跳过 skipped    : {len(importer.skipped)} (已在池中 / already in pool)")
    log(f"   失败 failed     : {len(importer.failed)}")
    log(f"   分组 group      : {group_id if group_id is not None else '未指定 / none'}")
    for name, err in list(importer.failed.items())[:10]:
        log(f"     ✗ {name}: {err[:200]}")
    log("─" * 62)

    if args.json_report:
        report = {
            "version": __version__,
            "batch_id": batch_id,
            "status": status,
            "produced": {"finished": finished, "ok": ok_count, "target": total},
            "imported": importer.imported,
            "skipped_existing": importer.skipped,
            "failed": importer.failed,
            "group_id": group_id,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        try:
            out = Path(args.json_report).expanduser()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"🧾 报告已写入 / report written: {out}")
        except OSError as exc:
            warn(f"报告写入失败 / cannot write report: {exc}")


def _exit_code(args: argparse.Namespace, importer: Importer, *, stalled: bool) -> int:
    if args.dry_run:
        return EXIT_OK
    if stalled:
        return EXIT_STALLED
    if importer.failed and importer.total:
        return EXIT_PARTIAL
    if importer.failed and not importer.total:
        return EXIT_ERROR
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"需要整数 / expected an integer, got {text!r}")
    if value < 1:
        raise argparse.ArgumentTypeError(f"必须 >= 1 / must be >= 1, got {value}")
    return value


def bounded_int(lo: int, hi: int):
    def _inner(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"需要整数 / expected an integer, got {text!r}")
        if not lo <= value <= hi:
            raise argparse.ArgumentTypeError(f"取值范围 {lo}..{hi} / out of range: {value}")
        return value

    return _inner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto_register_and_import.py",
        description=(
            "Grok 批量注册 + Sub2API 账号池导入 / Grok batch registration & Sub2API pool import "
            "(stdlib only, no pip installs required)"
        ),
        epilog=(
            "示例 / examples:\n"
            "  python3 scripts/auto_register_and_import.py --count 5\n"
            "  python3 scripts/auto_register_and_import.py --count 5 --dry-run\n"
            "  python3 scripts/auto_register_and_import.py --import-existing --accounts-dir /path/to/accounts\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    g = parser.add_argument_group("批次 / batch")
    g.add_argument("--count", type=bounded_int(1, 10000), default=1, help="要生产的账号数量 / accounts to produce (default: 1)")
    g.add_argument("--concurrency", type=bounded_int(1, 8), default=2, help="并发槽位 / parallel slots (default: 2)")
    g.add_argument("--stagger-ms", type=int, default=1500, help="启动错峰毫秒 / stagger delay (default: 1500)")
    g.add_argument("--target", default="grok", choices=["grok", "chatgpt"], help="注册目标 / registration target")
    g.add_argument("--registration-mode", choices=["browser", "protocol"], help="注册模式 / registration mode")
    g.add_argument("--mail-provider", help="覆盖收信渠道 / override mail provider (e.g. hotmail_local)")
    g.add_argument("--captcha-provider", choices=["local", "yescaptcha"], help="验证码渠道 / captcha provider")
    g.add_argument("--probe-model", default="grok-4.5", help="导入前探活模型 / probe model (default: grok-4.5)")
    g.add_argument("--skip-probe", action="store_true", help="跳过导入前探活 / disable pre-import probe")
    g.add_argument("--headed", action="store_true", help="有头浏览器（调试用）/ run browser headed")

    a = parser.add_argument_group("账号导入 / import")
    a.add_argument("--accounts-dir", help="凭据落盘目录 / credential dir (default: from ProGrok /api/output-paths)")
    a.add_argument("--group-id", type=int, help="Sub2API 分组 ID / group id (default: 2 or server config)")
    a.add_argument("--priority", type=int, default=50, help="账号优先级 / account priority (default: 50)")
    a.add_argument("--account-concurrency", type=int, default=3, help="单账号并发 / per-account concurrency (default: 3)")
    a.add_argument(
        "--import-existing",
        action="store_true",
        help="补齐模式：导入目录内全部历史账号（自动去重）/ backfill all historical files with dedupe",
    )
    a.add_argument(
        "--mtime-tolerance",
        type=float,
        default=180.0,
        help="文件 mtime 容差秒数 / mtime tolerance in seconds (default: 180)",
    )

    s = parser.add_argument_group("服务地址 / endpoints")
    s.add_argument("--progrok-url", default=os.getenv("PROGROK_API_URL", DEFAULT_PROGROK_URL), help="ProGrok 地址")
    s.add_argument("--novaapi-url", default=os.getenv("NOVAAPI_URL", ""), help="NovaApi 地址 (default: 8000 或服务端配置)")
    s.add_argument("--hotmail-url", default=os.getenv("HOTMAIL_HELPER_URL", DEFAULT_HOTMAIL_URL), help="Outlook 助手地址")
    s.add_argument("--solver-url", default=os.getenv("SOLVER_URL", DEFAULT_SOLVER_URL), help="Turnstile 求解器地址")
    s.add_argument("--admin-email", default="", help="NovaApi 管理员邮箱 / admin email")
    s.add_argument("--admin-password", default="", help="NovaApi 管理员密码 / admin password")
    s.add_argument("--api-key", default="", help="NovaApi API Key（api_key 模式）/ api key")
    s.add_argument("--auth-mode", choices=["password", "api_key"], help="NovaApi 认证方式 / auth mode")

    r = parser.add_argument_group("运行时 / runtime")
    r.add_argument("--poll-interval", type=float, default=8.0, help="进度轮询秒数 / poll interval (default: 8)")
    r.add_argument("--stall-timeout", type=float, default=900.0, help="无进度超时秒数 / stall timeout (default: 900)")
    r.add_argument("--max-wait", type=float, default=7200.0, help="整批最长等待秒数 / max wait (default: 7200, 0=不限)")
    r.add_argument("--request-timeout", type=float, default=20.0, help="单次请求超时 / request timeout (default: 20)")
    r.add_argument("--retries", type=int, default=2, help="网络重试次数 / HTTP retries (default: 2)")
    r.add_argument("--dry-run", action="store_true", help="只打印将要下发的参数，不创建批次 / print payload only")
    r.add_argument("--skip-preflight", action="store_true", help="跳过服务可达性自检 / skip preflight checks")
    r.add_argument("--json-report", help="摘要写入 JSON 文件 / write JSON report to path")
    r.add_argument("--env-file", default=".env", help="可选 .env 路径 / optional env file (default: .env)")
    r.add_argument("-v", "--verbose", action="store_true", help="详细日志 / verbose logging")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    global _VERBOSE
    parser = build_parser()
    args = parser.parse_args(argv)
    _VERBOSE = bool(args.verbose)

    if args.env_file:
        env_path = Path(args.env_file).expanduser()
        if not env_path.is_absolute():
            env_path = Path.cwd() / env_path
        loaded = load_env_file(env_path)
        if loaded:
            vlog(f"已从 {env_path} 载入 {loaded} 个环境变量 / loaded {loaded} env vars")

    # Re-apply env-derived defaults after .env load / .env 载入后刷新默认值
    if not args.progrok_url:
        args.progrok_url = DEFAULT_PROGROK_URL
    if not args.novaapi_url:
        args.novaapi_url = os.getenv("NOVAAPI_URL", "")
    if not args.accounts_dir:
        args.accounts_dir = os.getenv("GROK_ACCOUNTS_DIR", "")

    def _on_signal(signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):  # pragma: no cover - non-main thread
            pass

    try:
        return run_pipeline(args)
    except KeyboardInterrupt:
        warn("收到中断信号，已停止 / interrupted by user")
        return EXIT_INTERRUPTED
    except ApiError as exc:
        fail(str(exc))
        return EXIT_ERROR
    except Exception as exc:  # pragma: no cover - last-resort guard
        fail(f"未预期错误 / unexpected error: {exc!r}")
        if _VERBOSE:
            import traceback

            traceback.print_exc()
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
