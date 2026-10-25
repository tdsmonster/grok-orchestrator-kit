#!/usr/bin/env python3
"""
auto_register_and_import.py
=============================================================================
Agent 专属：Grok 自动化注册、OAuth 授权换票与 Sub2API 账号池原子导入脚本
=============================================================================
依赖库：
  pip install camoufox curl_cffi httpx
"""

import sys
import os
import json
import time
import argparse
import urllib.request
from pathlib import Path

# 配置参数
PROGROK_API = os.getenv("PROGROK_API", "http://127.0.0.1:3080")
NOVAAPI_URL = os.getenv("NOVAAPI_URL", "http://127.0.0.1:8000")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@novaapi.local")
ADMIN_PASS = os.getenv("ADMIN_PASS", "c8fdbc452d2e32c0e5b815e6")

def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def get_novaapi_token() -> str:
    login_data = json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASS}).encode()
    req = urllib.request.Request(
        f"{NOVAAPI_URL}/api/v1/auth/login",
        data=login_data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())["data"]["access_token"]

def start_registration_batch(count: int, domain: str, imap_user: str, imap_pass: str) -> str:
    payload = {
        "settings": {
            "registration_target": "grok",
            "registration_mode": "browser",
            "mail_provider": "custom",
            "mail_api_key": f"{imap_user}:{imap_pass}",
            "mail_base_url": "imaps://imap.gmail.com:993",
            "mail_domain": domain,
            "captcha_provider": "local",
            "local_solver_url": "http://127.0.0.1:5072",
            "count": count,
            "concurrency": 2,
            "stagger_ms": 1500,
            "probe_model": "grok-4.5",
            "pre_import_probe_enabled": True,
            "auto_import_enabled": False, # 由本脚本进行高可靠原子导入
            "registration_json_format": "sub2api",
            "grok_headless": True
        }
    }
    req = urllib.request.Request(
        f"{PROGROK_API}/api/register",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode())
        batch_id = res.get("batch_id")
        log(f"🚀 成功下发注册批次 [{batch_id}]，计划生产数量: {count}")
        return batch_id

def track_and_import(batch_id: str, accounts_dir: Path):
    jwt_token = get_novaapi_token()
    log("📡 开始持续追踪批次进度并流式导入 Sub2API...")
    imported_emails = set()

    while True:
        try:
            req = urllib.request.Request(f"{PROGROK_API}/api/batches/{batch_id}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                finished = data.get("finished", 0)
                total = data.get("count", 0)
                ok = data.get("ok_count", 0)
                status = data.get("status")

            # 扫描本地已落盘的新账号凭据
            for p in accounts_dir.glob("sub2api-*.json"):
                try:
                    d = json.load(open(p))
                    items = d.get("accounts", []) if "accounts" in d else [d]
                    for it in items:
                        name = it.get("name") or it.get("email")
                        if name and name not in imported_emails:
                            creds = it.get("credentials", {})
                            if creds.get("access_token") and creds.get("refresh_token"):
                                # 注入 Sub2API Group 2
                                payload = json.dumps({
                                    "name": name,
                                    "platform": "grok",
                                    "type": "oauth",
                                    "credentials": creds,
                                    "group_ids": [2],
                                    "concurrency": 3,
                                    "priority": 50,
                                    "status": "active"
                                }).encode()
                                req_acc = urllib.request.Request(
                                    f"{NOVAAPI_URL}/api/v1/admin/accounts",
                                    data=payload,
                                    headers={"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
                                )
                                with urllib.request.urlopen(req_acc, timeout=10) as resp_acc:
                                    res_acc = json.loads(resp_acc.read().decode())
                                    log(f"✅ 账号 [{name}] 成功录入 Sub2API (Group 2)! 状态: {res_acc.get('message')}")
                                    imported_emails.add(name)
                except Exception:
                    pass

            log(f"📊 批次进度: {finished}/{total} (成功={ok}) | 当前已入库={len(imported_emails)}")

            if status in ("done", "partial", "failed", "stopped") and finished >= total:
                log(f"🎉 批次 [{batch_id}] 全部执行结束！累计成功入库: {len(imported_emails)} 个账号。")
                break
        except Exception as e:
            log(f"⚠️ 状态跟踪告警: {e}")
        time.sleep(8)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grok Auto Register & Sub2API Import Pipeline")
    parser.add_argument("--count", type=int, default=1, help="Number of accounts to produce")
    parser.add_argument("--domain", type=str, default="gachoncopilot.com", help="Catch-all domain")
    parser.add_argument("--imap-user", type=str, default="congshaowei924@gmail.com", help="Gmail IMAP user")
    parser.add_argument("--imap-pass", type=str, default="pjmsexnqbxswuydb", help="Gmail App Password")
    parser.add_argument("--accounts-dir", type=str, default=str(Path.home() / "services/progrok/runtime/data/accounts"))
    args = parser.parse_args()

    batch_id = start_registration_batch(args.count, args.domain, args.imap_user, args.imap_pass)
    if batch_id:
        track_and_import(batch_id, Path(args.accounts_dir))
