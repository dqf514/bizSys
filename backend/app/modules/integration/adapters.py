"""三类外部适配器（占位实现）。

统一约定：enabled=False（settings 开关未开）时所有操作抛 ADAPTER_NOT_CONFIGURED；
二期对接时在各 Adapter 内实现真实调用，业务侧签名不变（ADR-0001 可替换适配层）。
"""

from app.core import response as R
from app.core.exceptions import BizException


class BaseAdapter:
    key = ""
    name = ""
    enabled = False  # 本期硬占位；接真实凭据后改为 settings 开关

    def _guard(self) -> None:
        if not self.enabled:
            raise BizException(R.ADAPTER_NOT_CONFIGURED, f"{self.name} 未配置/未启用（预留接口）")

    def status(self) -> dict:
        return {"key": self.key, "name": self.name, "enabled": self.enabled, "placeholder": True}


class WecomAdapter(BaseAdapter):
    """企业微信：SSO / 通讯录 / 微盘 / 消息。"""

    key = "wecom"
    name = "企业微信"

    GETTOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
    USERINFO_URL = "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo"
    MESSAGE_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

    def get_access_token(self, corp_id: str, secret: str) -> str:
        """corpId+secret 换 access_token，Redis 缓存（提前 200s 过期）。凭据来自 sys_config。

        注意：无真实凭据，本路径未实测（联调后移除本注释）。
        """
        import httpx

        from app.core.redis import get_redis

        cache_key = f"wecom:access_token:{corp_id}"
        r = get_redis()
        cached = r.get(cache_key)
        if cached:
            return cached
        resp = httpx.get(self.GETTOKEN_URL, params={"corpid": corp_id, "corpsecret": secret}, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            raise BizException(R.ADAPTER_NOT_CONFIGURED, f"企微 gettoken 失败：{data.get('errmsg', data)}")
        token = data["access_token"]
        r.setex(cache_key, max(int(data.get("expires_in", 7200)) - 200, 60), token)
        return token

    def sso_userid(self, corp_id: str, secret: str, code: str) -> str:
        """扫码/免登 code 换成员 userid（技术设计 §9.1）。未实测：需真实凭据。"""
        import httpx

        token = self.get_access_token(corp_id, secret)
        resp = httpx.get(self.USERINFO_URL, params={"access_token": token, "code": code}, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            raise BizException(R.ADAPTER_NOT_CONFIGURED, f"企微 getuserinfo 失败：{data.get('errmsg', data)}")
        userid = data.get("userid") or ""
        if not userid:  # 外部联系人/非成员扫码无 userid
            raise BizException(R.AUTH_WECOM_NOT_BOUND, "企微侧未返回成员 userid（仅企业成员可登录）")
        return userid

    def send_message(
        self,
        userid: str,
        content: str,
        *,
        corp_id: str,
        secret: str,
        agent_id: str,
        description: str = "",
        url: str = "",
    ) -> dict:
        """应用消息（textcard，含业务摘要+链接）。凭据由调用方从 sys_config 注入。

        注意：无真实凭据，本路径未实测（联调后移除本注释）。
        """
        import httpx

        if not (corp_id and secret and agent_id):
            raise BizException(R.ADAPTER_NOT_CONFIGURED, "企微凭据未配置")
        token = self.get_access_token(corp_id, secret)
        payload = {
            "touser": userid,
            "msgtype": "textcard",
            "agentid": int(agent_id),
            "textcard": {
                "title": content,
                "description": description or content,
                "url": url or "https://example.invalid/approval",
                "btntxt": "去处理",
            },
        }
        resp = httpx.post(self.MESSAGE_SEND_URL, params={"access_token": token}, json=payload, timeout=10)
        data = resp.json()
        if data.get("errcode") != 0:
            raise BizException(R.ADAPTER_NOT_CONFIGURED, f"企微消息发送失败：{data.get('errmsg', data)}")
        return data

    def get_org_tree(self) -> list:
        self._guard()
        return []

    def upload_disk_file(self, path: str) -> dict:
        self._guard()
        return {}


class MailAdapter(BaseAdapter):
    """腾讯企业邮箱。"""

    key = "mail"
    name = "企业邮箱"

    def send(self, to: list[str], subject: str, body: str) -> dict:
        self._guard()
        return {}


class WtcsAdapter(BaseAdapter):
    """WTCS 试验管理系统对接（任务推送/状态回写）。"""

    key = "wtcs"
    name = "WTCS"

    def push_task(self, task_no: str, payload: dict) -> dict:
        self._guard()
        return {}

    def pull_status(self, task_no: str) -> dict:
        self._guard()
        return {}


ADAPTERS: dict[str, BaseAdapter] = {a.key: a for a in (WecomAdapter(), MailAdapter(), WtcsAdapter())}
