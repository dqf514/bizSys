"""变更日志（Keep a Changelog + 语义化版本）。

**单一数据源 = 仓库根目录的 `CHANGELOG.md`**（代码拥有、随版本走，镜像内同样存在）。
后端只解析不改写：`GET /admin/changelog` 把 Markdown 解析成结构化条目供前端渲染。

条目格式（Keep a Changelog 1.1.0）::

    ## [0.7.0] - 2026-11-23
    ### Added
    - 变更说明

分类：`added` / `changed` / `deprecated` / `removed` / `fixed` / `security`，
未知分类原样透传（前端回退显示英文原名）。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Keep a Changelog 的六类（顺序即前端展示顺序）
SECTION_TYPES = ("added", "changed", "deprecated", "removed", "fixed", "security")

_VERSION_RE = re.compile(r"^##\s+(?P<body>.+?)\s*$")
_SECTION_RE = re.compile(r"^###\s+(?P<type>.+?)\s*$")
_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s+(?P<text>.+?)\s*$")
_DATE_RE = re.compile(r"[-–—]\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$")
_PAREN_DATE_RE = re.compile(r"\s*[（(]\s*\d{4}-\d{2}-\d{2}\s*[）)]\s*$")


@dataclass
class ChangelogItem:
    """一条变更；`children` 为缩进的子条目（一层）。"""

    text: str
    children: list[str] = field(default_factory=list)


@dataclass
class ChangelogSection:
    """一个分类（Added / Fixed / …）。"""

    type: str
    items: list[ChangelogItem] = field(default_factory=list)


@dataclass
class ChangelogRelease:
    """一个版本。"""

    version: str
    date: str
    sections: list[ChangelogSection] = field(default_factory=list)

    def out(self) -> dict:
        return {
            "version": self.version,
            "date": self.date,
            "sections": [
                {"type": s.type, "items": [{"text": i.text, "children": i.children} for i in s.items]}
                for s in self.sections
            ],
        }


def normalize_section_type(raw: str) -> str:
    """分类名归一：大小写 / 空格无关；未知分类保留原名（小写连字符形式）。"""
    key = raw.strip().lower().replace(" ", "-").replace("_", "-")
    return key or "other"


def _parse_release_header(line: str) -> tuple[str, str]:
    """解析 `## [0.7.0] - 2026-11-23` → ("0.7.0", "2026-11-23")。"""
    m = _VERSION_RE.match(line)
    body = (m.group("body") if m else line).strip()
    date = ""
    dm = _DATE_RE.search(body)
    if dm:
        date = dm.group("date")
        body = body[: dm.start()].strip()
    body = _PAREN_DATE_RE.sub("", body).strip()
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1].strip()
    return body, date


def parse_changelog(text: str) -> list[ChangelogRelease]:
    """解析 Keep a Changelog 文本 → 版本列表（保持文件中的顺序，新版在前）。"""
    releases: list[ChangelogRelease] = []
    release: ChangelogRelease | None = None
    section: ChangelogSection | None = None
    last_item: ChangelogItem | None = None
    in_fence = False

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        if line.startswith("## ") and not line.startswith("### "):
            version, date = _parse_release_header(line)
            release = ChangelogRelease(version=version, date=date)
            releases.append(release)
            section = None
            last_item = None
            continue

        if release is None:
            # 首个版本标题之前的内容（标题、说明、链接定义）忽略
            continue

        if line.startswith("### "):
            m = _SECTION_RE.match(line)
            section = ChangelogSection(type=normalize_section_type(m.group("type") if m else ""))
            release.sections.append(section)
            last_item = None
            continue

        m = _ITEM_RE.match(line)
        if m and section is not None:
            text_item = m.group("text").strip()
            indent = len(m.group("indent").expandtabs(4))
            if indent == 0:
                item = ChangelogItem(text=text_item)
                section.items.append(item)
                last_item = item
            elif last_item is not None:
                last_item.children.append(text_item)
            continue

        # 普通段落：结束当前条目上下文
        if line.strip():
            last_item = None

    return releases


def changelog_path() -> Path | None:
    """定位 `CHANGELOG.md`：环境变量 → 仓库根 → 工作目录 → 镜像内固定路径。"""
    candidates: list[Path] = []
    env_path = os.environ.get("CHANGELOG_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    # backend/app/modules/admin/changelog.py → parents[4] = 仓库根
    candidates.append(Path(__file__).resolve().parents[4] / "CHANGELOG.md")
    candidates.append(Path.cwd() / "CHANGELOG.md")
    candidates.append(Path("/app/CHANGELOG.md"))
    for path in candidates:
        if path.is_file():
            return path
    return None


_cache: tuple[str, float, list[ChangelogRelease]] | None = None


def load_releases() -> list[ChangelogRelease]:
    """读取并缓存解析结果（按文件 mtime 失效，改文件即时生效）。"""
    global _cache
    path = changelog_path()
    if path is None:
        return []
    mtime = path.stat().st_mtime
    if _cache and _cache[0] == str(path) and _cache[1] == mtime:
        return _cache[2]
    releases = parse_changelog(path.read_text(encoding="utf-8"))
    _cache = (str(path), mtime, releases)
    return releases
