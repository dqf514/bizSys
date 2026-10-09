# 企业微信扫码登录配置指南

> 对应功能：系统管理 → 系统与审计 → 系统设置（`/admin/settings`）。
> 技术设计依据：`技术设计文档.md` §9.1（SSO 扫码/免登）。凭据存储在 `sys_config` 表，Secret 经 AES-GCM 加密落库，接口永不返回明文。

## 一、创建自建应用并获取凭据

1. 用管理员账号登录企业微信管理后台：https://work.weixin.qq.com
2. 进入 **应用管理 → 应用 → 自建**，点击 **创建应用**：
   - 填写应用名称 / 简介 / 图标，可见范围选择需要扫码登录的成员（或整个企业）。
3. 创建后进入应用详情页，记录：
   - **AgentId**（应用 ID）
   - **Secret**（应用密钥，点击"查看"后通过企业微信客户端获取）
4. 进入 **我的企业** 页面，在底部记录 **企业 ID（CorpId）**。

## 二、在本系统填写参数

打开 **系统管理 → 系统设置 → 企业微信登录** 卡片：

| 字段 | 来源 |
|---|---|
| 企业 ID（CorpId） | 「我的企业」页底部 |
| 应用 AgentId | 自建应用详情页 |
| 应用 Secret | 自建应用详情页（留空表示不修改，已配置时输入框提示"已配置"） |
| 回调 URL | 默认 `<前端域名>/login`，需与前端部署地址一致 |

填写后保存。Secret 只在保存时传输一次，后端加密存储，之后接口只返回 `secretSet: true/false`。

## 三、配置可信域名与回调 URL

1. 在自建应用详情页找到 **企业微信授权登录**（网页授权登录），点击 **设置**。
2. 将 **授权回调域** 设置为前端部署域名（如 `bizsys.example.com`，不含协议和路径，需在企微侧完成域名归属校验：下载校验文件放到前端站点根目录）。
3. 本系统构造的扫码地址形如：

```
https://open.work.weixin.qq.com/wwopen/sso/qrConnect?appid=<CorpId>&agentid=<AgentId>&redirect_uri=<urlencode(回调URL)>&state=<随机串>
```

其中 `redirect_uri` 默认为 `GET /auth/wecom/qr-url` 时前端传入的 `${location.origin}/login`；如在系统设置中配置了回调 URL，则优先使用配置值。state 由后端生成并写入 Redis（10 分钟有效、一次性使用），用于防 CSRF。

## 四、绑定成员账号（userId ↔ 本地账号）

扫码授权后，企业微信返回的是成员 **UserId**，本系统按 `sys_user.wecom_userid` 字段映射本地账号：

- 企微成员的 UserId 可在管理后台「通讯录 → 成员详情」查看；
- 管理员将 UserId 写入对应本地用户的 `sys_user.wecom_userid` 字段（本期在数据库中维护，例如 `UPDATE sys_user SET wecom_userid='ZhangSan' WHERE username='zhangsan';`；后续版本计划在用户管理界面提供绑定入口）；
- 未绑定的成员扫码后返回业务错误码 **20005（企微账号未绑定本地用户）**。

## 五、扫码登录链路

```
① 登录页调 GET /api/v1/public/branding（免登录）→ wecomEnabled=true 时显示"企业微信扫码"页签
② 点击后调 GET /api/v1/auth/wecom/qr-url?redirect_uri=... → 跳转企微扫码页
③ 成员用企业微信扫码并授权 → 企微重定向回 <回调URL>?code=...&state=...
④ 前端调 POST /api/v1/auth/wecom/callback {code, state}
⑤ 后端校验 state → gettoken（corpId+secret，Redis 缓存 access_token）
   → auth/getuserinfo 用 code 换 userid → sys_user.wecom_userid 映射
   → 签发自有 JWT（返回结构与 /auth/login 一致）→ 进入应用外壳
```

开关生效顺序：填写凭据保存 → 打开「启用扫码登录」→ `branding.wecomEnabled` 变为 true。凭据不完整时开关保存不报错，但 `wecomEnabled` 保持 false、`qr-url` 返回 90001。

## 六、常见问题（FAQ）

- **扫码页提示"redirect_uri 与配置的授权回调域不一致"**：回调 URL 的域名未加入自建应用的授权回调域，或前端访问域名与配置不一致（注意 http/https、端口）。
- **回调返回 20006（state 无效或已过期）**：state 超过 10 分钟或已被使用，重新点击扫码登录即可。
- **回调返回 20005（未绑定）**：该企微成员的 UserId 未写入 `sys_user.wecom_userid`。
- **回调返回 90001**：未启用开关，或 CorpId/AgentId/Secret 未配齐，或企微接口调用失败（message 中含企微 errmsg，如 Secret 错误、IP 白名单未配置——自建应用需配置「企业可信 IP」）。
- **access_token 缓存**：后端按 CorpId 缓存 access_token（`wecom:access_token:<corpId>`，提前 200s 过期）；更换 Secret 后最多 2 分钟内自动失效，也可删除该 Redis 键立即生效。
- ** Secret 泄露处理**：在企微后台重置 Secret 后，在系统设置中重新填写保存即可（旧密文被覆盖）。
