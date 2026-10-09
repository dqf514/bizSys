"""鉴权接口入参/出参。"""

from pydantic import BaseModel, Field

from app.core.schemas import CamelModel


class LoginIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(CamelModel):
    refresh_token: str


class PasswordIn(CamelModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    dept_id: int | None = None
    dept_name: str = ""
    email: str = ""
    mobile: str = ""
    roles: list[str] = []
    perms: list[str] = []
    prefs: dict[str, str] = {}

    model_config = {"from_attributes": True}


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    user: UserOut


class MeOut(UserOut):
    menus: list = []
