# 🚀 Grok 账号自动裂变与高并发反代矩阵架构规范 (Agent 部署版)

本规范提炼自两大开源主力仓库：
1. **[ProGrok](https://github.com/xu16645-lang/progrok)**：无感指纹对抗注册、SSO 提取与 OAuth PKCE 授权置换引擎。
2. **[NovaApi (Sub2API 魔改分支)](https://github.com/AuuCoder/NovaApi)**：多账号高并发调度、额度平滑轮询与 OpenAI 格式协议反代集群。

本方案专为 **Agent / 自动化部署运维** 打造，剔除了冗余的前端编译和繁琐的手工配置，支持**一键 Docker 编排拉起 + 极简 Python 自动化投产**。

---

## 一、 核心技术拓扑与流水线 (Architecture Pipeline)

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. 邮箱与收信网络 (Catch-All Mail Pipeline)                  │
│  - 自定义域名 (Cloudflare Email Routing Catch-all)          │
│  - 任意邮箱前缀 xxx@yourdomain.com -> 转发至指定收信 Gmail   │
│  - 注册端通过 Gmail IMAP (imaps://imap.gmail.com:993) 秒级取码│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. ProGrok 自动注册与授权换票 (Registration & PKCE Worker)    │
│  - Camoufox 深度指纹隐匿浏览器 + 本地 Turnstile 求解器(:5072) │
│  - 自动向 accounts.x.ai 提交注册并提取 SSO 会话              │
│  - 触发本地 PKCE 授权换票：                                  │
│    Client ID: b1a00492-073a-47ea-816f-4c329264a828         │
│    Scope: openid profile email offline_access grok-cli:access│
│  - 产出标准 OAuth JSON 凭据 (含 access_token / refresh_token) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. NovaApi (Sub2API) 调度中枢与 OpenAI 反代 (Port: 8000)     │
│  - Postgres 18 持久化账号数据库 + Redis 8 高速并发令牌桶     │
│  - Upstream 绑定: https://cli-chat-proxy.grok.com/v1        │
│  - 账号自动注入 Group 2 (主力自用组) 或 Group 3 (对外分发)  │
│  - 对外暴露标准 OpenAI 兼容接口: /v1/chat/completions       │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、 关键技术指标与配置规范 (Technical Specs)

### 1. OAuth PKCE 核心参数 (xAI 官方协议)
- **Authorize URL**: `https://auth.x.ai/oauth2/authorize`
- **Token Exchange URL**: `https://auth.x.ai/oauth2/token`
- **Client ID**: `b1a00492-073a-47ea-816f-4c329264a828`
- **Redirect URI**: `http://127.0.0.1:56121/callback`
- **Scope**: `openid profile email offline_access grok-cli:access api:access`
- **Upstream Host**: `cli-chat-proxy.grok.com`

### 2. 标准入库凭证 JSON 结构 (Sub2API 规范)
Agent 生成并导入 NovaApi 账号池的 Payload 如下：
```json
{
  "name": "xxx@yourdomain.com",
  "platform": "grok",
  "type": "oauth",
  "credentials": {
    "access_token": "eyJ0eX...",
    "refresh_token": "yeS5-DE...",
    "token_type": "Bearer",
    "client_id": "b1a00492-073a-47ea-816f-4c329264a828",
    "scope": "openid profile email offline_access grok-cli:access api:access",
    "email": "xxx@yourdomain.com",
    "expires_at": "2026-10-25T12:00:00Z",
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

## 三、 Agent 极速部署指南 (Step-by-Step)

### 第 1 步：拉起 NovaApi 反代中枢
在 `compose/` 目录下执行：
```bash
docker compose up -d
```
服务将在本地 `http://127.0.0.1:8000` 监听。

### 第 2 步：配置邮箱与收信网络
1. 准备一个托管在 Cloudflare 上的域名，开启 **Email Routing ➔ Catch-all rule**，全部转发至你的 Gmail；
2. 获取 Gmail 的 **应用专用密码 (App Password)**；
3. 将参数填入 `scripts/auto_register_and_import.py` 中。

### 第 3 步：运行全自动生产脚本
```bash
python3 scripts/auto_register_and_import.py --count 5
```
脚本将全自动唤醒指纹浏览器完成注册、收取验证码、PKCE 授权换票，并将 5 个账号安全无缝地挂载到 NovaApi 的 Grok 账号池中！
