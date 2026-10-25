# 🚀 Grok-Orchestrator-Kit (GOK)

<div align="center">

<h3>⚡ Automated xAI Grok Account Harvester & High-Concurrency OpenAI-Compatible Gateway ⚡</h3>
<p><b>全自动 xAI Grok 账号裂变收割机与高并发 OpenAI 兼容反向代理中枢</b></p>

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](compose/docker-compose.yml)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-412991?style=flat-square&logo=openai&logoColor=white)](docs/ARCHITECTURE_SPEC.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](scripts/auto_register_and_import.py)
[![Architecture](https://img.shields.io/badge/Target-Agent%20Native-00C7B7?style=flat-square)](docs/ARCHITECTURE_SPEC.md)

<p align="center">
  <a href="#-overview--项目概述">Overview</a> •
  <a href="#-key-features--核心特性">Features</a> •
  <a href="#-architecture--系统架构">Architecture</a> •
  <a href="#-quick-start--快速上手">Quick Start</a> •
  <a href="#-email-pipeline--邮箱裂变机制">Email Pipeline</a> •
  <a href="#-technical-specifications--关键技术指标">Tech Specs</a> •
  <a href="#-license--开源协议">License</a>
</p>

---

</div>

## 📖 Overview / 项目概述

**English:**  
**Grok-Orchestrator-Kit (GOK)** is a production-grade, agent-native toolkit distilled from top-tier community tools ([`ProGrok`](https://github.com/xu16645-lang/progrok) & [`NovaApi`](https://github.com/AuuCoder/NovaApi)). It delivers an autonomous end-to-end pipeline:
1. Automated email harvesting & verification (via Cloudflare Email Routing Catch-all or Microsoft Outlook Plus-Addressing);
2. Anti-detection browser registration & official xAI OAuth PKCE token exchange;
3. Seamless credential hydration into a high-concurrency PostgreSQL + Redis proxy cluster with standard OpenAI-compatible endpoints (`/v1/chat/completions`).

**中文：**  
**Grok-Orchestrator-Kit (GOK)** 是一套面向 AI Agent 与自动化运维场景的工业级生产套件，提炼自开源主力项目（[`ProGrok`](https://github.com/xu16645-lang/progrok) 与 [`NovaApi`](https://github.com/AuuCoder/NovaApi)）。它实现了完整的无人值守自动化闭环：
1. 邮箱裂变收割与验证码毫秒级提取（支持 Cloudflare 域名 Catch-all 与 微软 Outlook 加号别名）；
2. Camoufox 深度隐匿指纹浏览器自主过人机验证并完成 xAI 官方 OAuth PKCE 换票；
3. 凭据秒级挂载进基于 PostgreSQL 18 + Redis 8 的高并发负载池，对外输出标准 OpenAI 格式接口。

---

## 🌟 Key Features / 核心特性

- 🛡️ **Headless Anti-Detection Registration / 无感指纹隐匿注册**  
  Powered by `Camoufox` and local Turnstile bypass techniques, effortlessly negotiating Cloudflare challenges and extracting authentic xAI SSO credentials.  
  依托 Camoufox 隐匿内核与本地求解器，全自动跨越 Cloudflare 盾并提取 xAI 原始 SSO 会话。

- 🔑 **Native xAI OAuth PKCE Token Exchange / 官方原生 PKCE 换票**  
  Strictly compliant with official xAI CLI specifications (`b1a00492-073a-47ea-816f-4c329264a828`), exchanging browser sessions for official `access_token` and `refresh_token` with background auto-rotation.  
  严格遵循 xAI 官方标准协议，将浏览器 Session 置换为官方 OAuth 凭据，支持静默自动刷新续期。

- 📬 **Dual Email Scaling Pipelines / 双重邮箱无限裂变架构**  
  - **Custom Domain Catch-All**: Routes any random prefix (`*@domain.com`) directly to Gmail IMAP.  
  - **Microsoft Outlook Plus-Addressing**: 1 master account spawns 10 valid registration addresses (`base+1@outlook.com` ... `base+9@outlook.com`) via Graph API.  
  - **自定义域名全员捕获**：基于 Cloudflare Email Routing，任意邮箱别名统一汇聚至 Gmail IMAP。  
  - **微软加号别名裂变**：单个 Outlook 母号通过 `+tag` 原生派生 10 个独立注册账号，通过 Graph API 极速收信。

- ⚡ **High-Concurrency Rate-Limited Hub / 高并发池化调度中枢 (NovaApi)**  
  Built-in PostgreSQL 18 persistence, Redis 8 distributed token-bucket rate limiting, smooth round-robin scheduling, and automatic fault isolation for dead accounts.  
  内建 PostgreSQL 18 持久化储存与 Redis 8 令牌桶并发调度，支持多账号平滑轮询与失效账号物理隔离。

- 🤖 **Agent-First Minimalist Footprint / Agent 极简零阻碍交付**  
  Stripped of all cumbersome frontend compilation, WebUI overhead, and delicate dev-dependencies. Clean Docker Compose orchestration and headless Python automation.  
  剥离一切冗余的前端打包编译与沉重 UI，纯声明式 Docker 编排与无头 Python 驱动，开箱即用。

---

## 🏗️ Architecture / 系统架构

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Mail Scaling Network / 邮箱裂变网络                                    │
│   • Route A: Cloudflare Catch-All (*@yourdomain.com -> Gmail IMAP)     │
│   • Route B: Microsoft Outlook Plus-Addressing (base+N@outlook.com)    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. Automated Harvester & PKCE Exchanger / 自动化注册与授权换票中枢        │
│   • Camoufox Anti-Detect Browser Engine                                │
│   • Cloudflare Turnstile Solver (:5072)                                │
│   • xAI PKCE Flow -> Client ID: b1a00492-073a-47ea-816f-4c329264a828  │
│   • Output: Standardized OAuth JSON Credentials                        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. NovaApi (Sub2API) High-Concurrency Gateway / 高并发反代中枢 (:8000)   │
│   • Upstream Target: https://cli-chat-proxy.grok.com/v1                │
│   • PostgreSQL 18 State Persistence + Redis 8 Concurrency Token Bucket │
│   • Auto Account Grouping (Group 2: Grok VIP Pool)                     │
│   • OpenAI Endpoint: POST /v1/chat/completions (Model: grok-4.5)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start / 快速上手

### 1. Clone Repository / 克隆仓库
```bash
git clone https://github.com/tdsmonster/grok-orchestrator-kit.git
cd grok-orchestrator-kit
```

### 2. Boot Gateway Cluster / 启动反向代理集群
```bash
cd compose
docker compose up -d
```
> The gateway will listen on `http://localhost:8000`. PostgreSQL and Redis will automatically self-initialize and apply migrations.  
> 启动后反代网关监听于 `http://localhost:8000`，数据库与缓存层全自动完成无状态迁移。

### 3. Run Automated Harvesting / 执行自动化账号生产
```bash
# Return to root directory / 返回根目录
cd ..

# Install minimal worker requirements / 安装极简运行时依赖
pip install curl_cffi httpx

# Run 5-account automated generation & injection
# 启动 5 个账号的自动注册与注入
python3 scripts/auto_register_and_import.py \
  --count 5 \
  --domain "yourdomain.com" \
  --imap-user "your_gmail@gmail.com" \
  --imap-pass "your_gmail_app_password"
```

---

## 📬 Email Pipeline / 邮箱裂变机制

| Mode / 模式 | Mechanism / 实现机制 | Scaling Ratio / 扩容杠杆 | Best Suited For / 适用场景 |
| :--- | :--- | :--- | :--- |
| **Catch-All Domain** | Cloudflare Email Routing forwards `*@domain.com` to Gmail | **Infinite (1:∞)** / 无限裂变 | Long-term cluster operations, custom domain owners<br>长期高并发集群运营、有独立域名者 |
| **Outlook Plus** | Microsoft Plus-Addressing (`base+1@outlook.com`) via Graph API | **1:10 per mailbox** / 1 母号裂变 10 子号 | Fast cold starts, zero-domain setup, disposable pools<br>无域名快速冷启动、一次性账号池补给 |

---

## 📑 Technical Specifications / 关键技术指标

### xAI Official OAuth PKCE Protocol / 官方协议标准
```yaml
Authorize URL:       https://auth.x.ai/oauth2/authorize
Token Exchange URL:  https://auth.x.ai/oauth2/token
Official Client ID:  b1a00492-073a-47ea-816f-4c329264a828
Redirect URI:        http://127.0.0.1:56121/callback
Scope:               openid profile email offline_access grok-cli:access api:access
Upstream Target:     https://cli-chat-proxy.grok.com/v1
```

### Standard Credential Structure / 标准入库凭证格式
```json
{
  "name": "account_alias@domain.com",
  "platform": "grok",
  "type": "oauth",
  "credentials": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...",
    "refresh_token": "yeS5-DE22gbIGQh27kDUscrUfjsiIMgiKRHzaLve...",
    "token_type": "Bearer",
    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
    "scope": "openid profile email offline_access grok-cli:access api:access",
    "email": "account_alias@domain.com",
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

## 🧪 Verifying Gateway Output / 验证反代端点

Once accounts are loaded, query the gateway via any OpenAI SDK or `curl`:  
账号录入后，可通过标准 OpenAI SDK 或 `curl` 验证输出：

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

## 📄 License / 开源协议

Distributed under the [MIT License](LICENSE).  
本项目基于 [MIT 开源协议](LICENSE) 发布。
