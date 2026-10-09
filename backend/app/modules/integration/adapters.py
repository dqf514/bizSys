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

    def send_message(self, userid: str, content: str) -> dict:
        self._guard()
        return {}

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
