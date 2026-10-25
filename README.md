# ⚡ GROK-ORCHESTRATOR-KIT (GOK)

<div align="center">

# 🚀 GROK-ORCHESTRATOR-KIT
### ⚡ Automated xAI Grok Account Harvester & High-Concurrency OpenAI-Compatible Gateway ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](compose/docker-compose.yml)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-412991?style=for-the-badge&logo=openai&logoColor=white)](docs/ARCHITECTURE_SPEC.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](scripts/auto_register_and_import.py)
[![Architecture](https://img.shields.io/badge/Target-Agent%20Native-00C7B7?style=for-the-badge)](docs/ARCHITECTURE_SPEC.md)

<p align="center">
  <b>English</b> | <a href="README_CN.md"><b>简体中文</b></a>
</p>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-key-features">Key Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-outlook-plus-addressing">Outlook Scaling</a> •
  <a href="#-technical-specifications">Tech Specs</a> •
  <a href="#-verifying-the-gateway">Verifying Output</a> •
  <a href="#-license">License</a>
</p>

---

</div>

## 📖 OVERVIEW

**GROK-ORCHESTRATOR-KIT (GOK)** is a production-grade, agent-native toolkit distilled from top-tier community projects ([`ProGrok`](https://github.com/xu16645-lang/progrok) & [`NovaApi`](https://github.com/AuuCoder/NovaApi)). It delivers a fully autonomous end-to-end pipeline:

1. **Outlook Plus-Addressing Harvesting**: High-speed, 10x email alias expansion and instant code extraction via Microsoft Graph API.
2. **Headless Anti-Detection Registration**: Camoufox fingerprint masking combined with local Cloudflare Turnstile solving and official xAI OAuth PKCE token exchange.
3. **High-Concurrency Dispatching**: Seamless credential hydration into a PostgreSQL 18 + Redis 8 proxy cluster exposing standard OpenAI-compatible endpoints (`/v1/chat/completions`).

---

## 🌟 KEY FEATURES

- 🛡️ **HEADLESS ANTI-DETECTION REGISTRATION**  
  Powered by `Camoufox` and local Turnstile bypass techniques, effortlessly negotiating Cloudflare challenges and extracting authentic xAI SSO sessions.

- 🔑 **NATIVE xAI OAUTH PKCE TOKEN EXCHANGE**  
  Strictly compliant with official xAI CLI specifications (`b1a00492-073a-47ea-816f-4c329264a828`), exchanging browser sessions for official `access_token` and `refresh_token` with background auto-rotation.

- 📬 **MICROSOFT OUTLOOK PLUS-ADDRESSING SCALING**  
  Leverages RFC 5233 plus-addressing. A single master mailbox spawns 10 valid registration addresses (`base+1@outlook.com` ... `base+9@outlook.com`) with instant code fetching via Microsoft Graph API.

- ⚡ **HIGH-CONCURRENCY RATE-LIMITED HUB (NOVAAPI)**  
  Built-in PostgreSQL 18 persistence, Redis 8 distributed token-bucket rate limiting, smooth round-robin scheduling, and automatic fault isolation for dead accounts.

- 🤖 **AGENT-FIRST MINIMALIST FOOTPRINT**  
  Stripped of all cumbersome frontend compilation, WebUI overhead, and delicate dev-dependencies. Clean Docker Compose orchestration and headless Python automation.

---

## 🏗️ ARCHITECTURE

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. OUTLOOK PLUS-ADDRESSING SCALING NETWORK                             │
│   • Microsoft Master Mailbox (base@outlook.com)                        │
│   • Automatic 10x Plus-Alias Expansion (base+1@outlook.com ... +9)     │
│   • Microsoft Graph API Helper (:17373) -> Real-Time Code Extraction   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. AUTOMATED HARVESTER & PKCE EXCHANGER                                │
│   • Camoufox Anti-Detect Browser Engine                                │
│   • Cloudflare Turnstile Solver (:5072)                                │
│   • xAI PKCE Flow -> Client ID: b1a00492-073a-47ea-816f-4c329264a828  │
│   • Output: Standardized OAuth JSON Credentials                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. NOVAAPI (SUB2API) HIGH-CONCURRENCY GATEWAY (:8000)                  │
│   • Upstream Target: https://cli-chat-proxy.grok.com/v1                │
│   • PostgreSQL 18 State Persistence + Redis 8 Concurrency Token Bucket │
│   • Auto Account Grouping (Group 2: Grok VIP Pool)                     │
│   • OpenAI Endpoint: POST /v1/chat/completions (Model: grok-4.5)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 QUICK START

### 1. CLONE REPOSITORY
```bash
git clone https://github.com/tdsmonster/grok-orchestrator-kit.git
cd grok-orchestrator-kit
```

### 2. BOOT GATEWAY CLUSTER
```bash
cd compose
docker compose up -d
```
> The gateway will listen on `http://localhost:8000`. PostgreSQL and Redis will automatically self-initialize and apply migrations.

### 3. RUN AUTOMATED HARVESTING
```bash
# Return to root directory
cd ..

# Install minimal worker requirements
# 纯标准库驱动，无需额外 pip 安装第三方网络库 (Zero external dependencies)

# Run 5-account automated generation & injection via Outlook Plus
python3 scripts/auto_register_and_import.py --count 5
```

---

## 📬 OUTLOOK PLUS-ADDRESSING

| PARAMETER | SPECIFICATION |
| :--- | :--- |
| **Protocol** | Microsoft Graph API / OAuth 2.0 |
| **Expansion Ratio** | **1:10** (1 Master Mailbox -> 10 Autonomous Accounts) |
| **Address Pattern** | `base+1@outlook.com`, `base+2@outlook.com`, ... |
| **Local Helper Service**| `http://127.0.0.1:17373` |

---

## 📑 TECHNICAL SPECIFICATIONS

### xAI OFFICIAL OAUTH PKCE PROTOCOL
```yaml
Authorize URL:       https://auth.x.ai/oauth2/authorize
Token Exchange URL:  https://auth.x.ai/oauth2/token
Official Client ID:  b1a00492-073a-47ea-816f-4c329264a828
Redirect URI:        http://127.0.0.1:56121/callback
Scope:               openid profile email offline_access grok-cli:access api:access
Upstream Target:     https://cli-chat-proxy.grok.com/v1
```

### STANDARD CREDENTIAL STRUCTURE
```json
{
  "name": "username+1@outlook.com",
  "platform": "grok",
  "type": "oauth",
  "credentials": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
    "refresh_token": "yeS5-DE22gbIGQh27kDUscrUfjsiIMgiKRHzaLve...",
    "token_type": "Bearer",
    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
    "scope": "openid profile email offline_access grok-cli:access api:access",
    "email": "username+1@outlook.com",
    "expires_at": "2026-10-25T18:00:00Z",
    "base_url": "https://cli-chat-proxy.grok.com/v1"
  },
  "concurrency": 3,
  "priority": 50,
  "rate_multiplier": 1.0,
  "auto_pause_on_expired": true,
  "group_ids": [2]
}
```

---

## 🧪 VERIFYING THE GATEWAY

Once accounts are loaded, query the gateway via any OpenAI SDK or `curl`:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer friend-vip-3" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "grok-4.5",
    "messages": [{"role": "user", "content": "Ping!"}]
  }'
```

---

## 📄 LICENSE

Distributed under the [MIT License](LICENSE).
