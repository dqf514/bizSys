"""系统设置接口 Schemas。"""

from pydantic import Field

from app.core.schemas import CamelModel


class WecomIn(CamelModel):
    enabled: bool = False
    corp_id: str = Field(default="", max_length=64)
    agent_id: str = Field(default="", max_length=32)
    secret: str = Field(default="", max_length=128)  # 空串 = 不修改
    callback_url: str = Field(default="", max_length=255)


# ---------------- 消息通道（邮件 SMTP / 短信） ----------------


class EmailIn(CamelModel):
    host: str = Field(default="", max_length=128)
    port: int = Field(default=0, ge=0, le=65535)  # 0 = 按 security 取默认端口
    security: str = Field(default="ssl", pattern=r"^(ssl|starttls|none)$")
    username: str = Field(default="", max_length=128)
    password: str = Field(default="", max_length=128)  # 空串 = 不修改
    sender: str = Field(default="", max_length=128)


class SmsAliyunIn(CamelModel):
    access_key_id: str = Field(default="", max_length=128)
    access_key_secret: str = Field(default="", max_length=128)  # 空串 = 不修改
    sign_name: str = Field(default="", max_length=64)
    template_code: str = Field(default="", max_length=64)


class SmsTencentIn(CamelModel):
    secret_id: str = Field(default="", max_length=128)
    secret_key: str = Field(default="", max_length=128)  # 空串 = 不修改
    sdk_app_id: str = Field(default="", max_length=64)
    sign_name: str = Field(default="", max_length=64)
    template_id: str = Field(default="", max_length=64)


class SmsHuaweiIn(CamelModel):
    app_key: str = Field(default="", max_length=128)
    app_secret: str = Field(default="", max_length=128)  # 空串 = 不修改
    sender: str = Field(default="", max_length=64)
    template_id: str = Field(default="", max_length=64)


class SmsCustomHttpIn(CamelModel):
    url: str = Field(default="", max_length=255)
    param_template: str = Field(default="", max_length=512)  # JSON 模板，{phone}/{code} 占位
    auth_header: str = Field(default="", max_length=255)  # 空串 = 不修改


class SmsIn(CamelModel):
    provider: str = Field(default="", pattern=r"^(|aliyun|tencent|huawei|custom_http)$")
    aliyun: SmsAliyunIn | None = None
    tencent: SmsTencentIn | None = None
    huawei: SmsHuaweiIn | None = None
    custom_http: SmsCustomHttpIn | None = None


class MessagingIn(CamelModel):
    email: EmailIn | None = None
    sms: SmsIn | None = None


class MessagingTestIn(CamelModel):
    channel: str = Field(pattern=r"^(sms|email)$")
    target: str = Field(min_length=1, max_length=128)


class WecomCallbackIn(CamelModel):
    code: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=64)


class SettingsIn(CamelModel):
    site_name: str | None = Field(default=None, max_length=128)
    wecom: WecomIn | None = None
    messaging: MessagingIn | None = None
