# ⚡ GROK-ORCHESTRATOR-KIT (GOK)

<div align="center">

# 🚀 GROK-ORCHESTRATOR-KIT
### ⚡ 全自动 xAI GROK 账号裂变收割机与高并发 OPENAI 兼容反向代理中枢 ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)](compose/docker-compose.yml)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-412991?style=for-the-badge&logo=openai&logoColor=white)](docs/ARCHITECTURE_SPEC.md)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](scripts/auto_register_and_import.py)
[![Architecture](https://img.shields.io/badge/Target-Agent%20Native-00C7B7?style=for-the-badge)](docs/ARCHITECTURE_SPEC.md)

<p align="center">
  <a href="README.md"><b>English</b></a> | <b>简体中文</b>
</p>

<p align="center">
  <a href="#-项目概述">项目概述</a> •
  <a href="#-核心特性">核心特性</a> •
  <a href="#-系统架构">系统架构</a> •
  <a href="#-快速上手">快速上手</a> •
  <a href="#-微软-outlook-邮箱裂变机制">Outlook 裂变</a> •
  <a href="#-关键技术指标">技术指标</a> •
  <a href="#-验证反代端点">验证输出</a> •
  <a href="#-开源协议">开源协议</a>
</p>

---

</div>

## 📖 项目概述

**GROK-ORCHESTRATOR-KIT (GOK)** 是一套专为 AI Agent 与自动化运维场景打造的工业级生产套件，提炼自开源主力工程（[`ProGrok`](https://github.com/xu16645-lang/progrok) 与 [`NovaApi`](https://github.com/AuuCoder/NovaApi)）。它实现了完整的无人值守自动化闭环：

1. **微软 Outlook 别名裂变**：基于微软原生 Plus-Addressing 规范与 Graph API，实现单个母号 10 倍裂变与验证码毫秒级自动捕获。
2. **无感指纹隐匿注册**：Camoufox 深度隐匿浏览器结合本地 Turnstile 求解器，自动跨越安全挑战并触发官方 xAI OAuth PKCE 授权换票。
3. **高并发池化分发**：凭据秒级挂载进基于 PostgreSQL 18 + Redis 8 的调度集群，对外暴露标准的 OpenAI 格式端点（`/v1/chat/completions`）。

---

## 🌟 核心特性

- 🛡️ **无感指纹隐匿注册**  
  依托 `Camoufox` 浏览器内核与本地验证码求解器，轻松通过 Cloudflare 人机对抗，提取真实 xAI 原始 SSO 会话。

- 🔑 **官方原生 xAI OAUTH PKCE 换票**  
  严格遵循 xAI 官方标准协议（Client ID: `b1a00492-073a-47ea-816f-4c329264a828`），将浏览器 Session 置换为官方 `access_token` 与带续期权限的 `refresh_token`。

- 📬 **微软 OUTLOOK / HOTMAIL 深度裂变架构**  
  单个 Outlook/Hotmail 母号通过 `+tag` 加号规范原生派生 10 个独立注册账号，通过微软 Graph API 极速提取验证码。

- ⚡ **高并发池化调度中枢 (NOVAAPI)**  
  内建 PostgreSQL 18 持久化储存与 Redis 8 令牌桶并发调度，支持多账号平滑轮询与失效账号物理隔离。

- 🤖 **AGENT 极简零阻碍交付**  
  剥离一切冗余的前端打包编译与沉重 UI，纯声明式 Docker 编排与无头 Python 驱动，开箱即用。

---

## 🏗️ 系统架构

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. 微软 OUTLOOK 别名裂变网络 (OUTLOOK PLUS-ADDRESSING)                 │
│   • 微软母号池 (base@outlook.com)                                      │
│   • 自动 10 倍加号别名派生 (base+1@outlook.com ... base+9@outlook.com)│
│   • 微软 Graph API 助手 (:17373) -> 验证码毫秒级提取                   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. 自动化注册与授权换票中枢 (HARVESTER & PKCE EXCHANGER)               │
│   • Camoufox 指纹隐匿浏览器引擎                                        │
│   • 本地 Turnstile 求解器 (:5072)                                      │
│   • xAI PKCE 流程 -> Client ID: b1a00492-073a-47ea-816f-4c329264a828  │
│   • 产出物: 标准化 OAuth JSON 凭证文件                                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. NOVAAPI (SUB2API) 高并发反代中枢 (:8000)                            │
│   • 上游目标: https://cli-chat-proxy.grok.com/v1                       │
│   • PostgreSQL 18 持久化存储 + Redis 8 分布式并发令牌桶                │
│   • 账号自动分组 (Group 2: Grok VIP 账号池)                            │
│   • OpenAI 兼容端点: POST /v1/chat/completions (Model: grok-4.5)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速上手

### 1. 克隆仓库
```bash
git clone https://github.com/tdsmonster/grok-orchestrator-kit.git
cd grok-orchestrator-kit
```

### 2. 启动反向代理集群
```bash
cd compose
docker compose up -d
```
> 反代中枢将在 `http://localhost:8000` 监听。PostgreSQL 和 Redis 将全自动完成无状态迁移。

### 3. 执行自动化账号生产
```bash
# 返回项目根目录
cd ..

# 安装极简依赖
# 纯标准库驱动，无需额外 pip 安装第三方网络库 (Zero external dependencies)

# 启动 5 个账号的自动注册与注入 (自动走 Outlook 裂变)
python3 scripts/auto_register_and_import.py --count 5
```

---

## 📬 微软 OUTLOOK 邮箱裂变机制

| 核心参数 | 规范定义 |
| :--- | :--- |
| **底层协议** | 微软官方 Graph API / OAuth 2.0 |
| **裂变杠杆** | **1:10** (1 个微软母号派生 10 个独立 xAI 账号) |
| **地址衍生格式** | `base+1@outlook.com`, `base+2@outlook.com`, ... |
| **本地收信服务** | `http://127.0.0.1:17373` |

---

## 📑 关键技术指标

### xAI 官方 OAUTH PKCE 协议标准
```yaml
Authorize URL:       https://auth.x.ai/oauth2/authorize
Token Exchange URL:  https://auth.x.ai/oauth2/token
Official Client ID:  b1a00492-073a-47ea-816f-4c329264a828
Redirect URI:        http://127.0.0.1:56121/callback
Scope:               openid profile email offline_access grok-cli:access api:access
Upstream Target:     https://cli-chat-proxy.grok.com/v1
```

### 标准入库凭证 JSON 格式
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

## 🧪 验证反代端点

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

## 📄 开源协议

本项目遵循 [MIT 开源协议](LICENSE)。
