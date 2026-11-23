"""变更日志（Keep a Changelog + 语义化版本）。

覆盖：
- `GET /admin/changelog` 返回结构（当前版本 / 版本列表 / 分类条目）；
- 未登录访问被拒；
- 仓库根 `CHANGELOG.md` 顶部版本与应用版本号三处一致、版本号严格递减；
- Markdown 解析器（多分类 / 缩进子条目 / 未知分类 / Unreleased）。
"""

import json
import re
from pathlib import Path

from app.core.config import settings
from app.modules.admin.changelog import SECTION_TYPES, parse_changelog

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG_FILE = REPO_ROOT / "CHANGELOG.md"


def _data(resp):
    body = resp.json()
    assert body["code"] == 0, body
    return body["data"]


def _vkey(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def test_changelog_endpoint(client, admin_headers):
    data = _data(client.get("/api/v1/admin/changelog", headers=admin_headers))
    assert data["currentVersion"] == settings.app_version
    assert data["releases"], "变更日志不能为空"
    assert data["latestVersion"] == data["releases"][0]["version"]
    first = data["releases"][0]
    assert first["date"]
    assert first["sections"]
    for section in first["sections"]:
        assert section["type"] in SECTION_TYPES
        assert section["items"]
        for item in section["items"]:
            assert item["text"]
            assert isinstance(item["children"], list)


def test_changelog_requires_login(client):
    resp = client.get("/api/v1/admin/changelog")
    assert resp.status_code == 401


def test_changelog_versions_consistent():
    """CHANGELOG.md 顶部版本 == 应用版本号 == package.json == pyproject.toml。"""
    text = CHANGELOG_FILE.read_text(encoding="utf-8")
    releases = parse_changelog(text)
    assert releases, "CHANGELOG.md 解析不出任何版本"
    versions = [r.version for r in releases]
    assert versions[0] == settings.app_version, f"变更日志顶部版本 {versions[0]} != {settings.app_version}"
    # 版本号严格递减
    assert [_vkey(v) for v in versions] == sorted((_vkey(v) for v in versions), reverse=True)
    # 每个版本都要有日期与至少一个分类
    for r in releases:
        assert r.date, f"{r.version} 缺少发布日期"
        assert r.sections, f"{r.version} 缺少变更条目"

    pkg = json.loads((REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert pkg["version"] == settings.app_version

    pyproject = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version = "([^"]+)"', pyproject, flags=re.M)
    assert m and m.group(1) == settings.app_version


def test_parse_changelog_sample():
    text = """# 变更日志

前言与链接定义忽略。

## [1.2.0] - 2026-11-23
### Added
- 新增一条
  - 缩进子条目
### Fixed
- 修复一条

## [Unreleased]

### Added
- 待发布
"""
    releases = parse_changelog(text)
    assert len(releases) == 2

    first = releases[0]
    assert first.version == "1.2.0"
    assert first.date == "2026-11-23"
    assert [s.type for s in first.sections] == ["added", "fixed"]
    assert first.sections[0].items[0].text == "新增一条"
    assert first.sections[0].items[0].children == ["缩进子条目"]
    assert first.sections[1].items[0].text == "修复一条"

    second = releases[1]
    assert second.version == "Unreleased"
    assert second.date == ""
    assert second.sections[0].items[0].text == "待发布"


def test_parse_changelog_unknown_section():
    """未登记的分类原样透传（前端回退显示原名）。"""
    releases = parse_changelog("## [0.1.0] - 2026-01-01\n### Removed\n- 移除一条\n### Internal\n- 内部条目\n")
    assert len(releases) == 1
    assert [s.type for s in releases[0].sections] == ["removed", "internal"]
