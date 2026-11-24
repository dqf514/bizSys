"""菜单标题 i18n 守卫。

后端菜单种子 `MENU_TREE` 的第一列是 `title_key`（形如 `menu.entrustList`），
前端侧边导航 / 顶栏标题 / 命令面板 / Dock 全部用 `t(titleKey)` 取标题 ——
**词条缺失时 vue-i18n 直接回显原始键名**（界面出现 `menu.entrustList` 这种"乱码"）。

所以：种子里的每个 `menu.*` 标题键都必须在 `frontend/src/locales/{zh-CN,en-US}/menu.json`
有对应词条（中英键集必须一致）。
"""

import json
from pathlib import Path

from app.seeds.init_data import MENU_TREE

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCALE_DIR = REPO_ROOT / "frontend" / "src" / "locales"


def _seed_title_keys() -> set[str]:
    keys: set[str] = set()

    def walk(nodes):
        for node in nodes:
            title_key = node[0]
            if isinstance(title_key, str) and title_key.startswith("menu."):
                keys.add(title_key.split(".", 1)[1])
            children = node[6] if len(node) > 6 else []
            if children:
                walk(children)

    walk(MENU_TREE)
    return keys


def test_seed_menu_titles_have_locales():
    keys = _seed_title_keys()
    assert keys, "MENU_TREE 里解析不到任何菜单标题键"
    for loc in ("zh-CN", "en-US"):
        data = json.loads((LOCALE_DIR / loc / "menu.json").read_text(encoding="utf-8"))
        missing = sorted(k for k in keys if k not in data)
        assert not missing, f"{loc}/menu.json 缺少菜单标题词条：{missing}（界面会显示原始键名）"


def test_menu_locales_key_sets_match():
    zh = json.loads((LOCALE_DIR / "zh-CN" / "menu.json").read_text(encoding="utf-8"))
    en = json.loads((LOCALE_DIR / "en-US" / "menu.json").read_text(encoding="utf-8"))
    assert set(zh) == set(en), f"中英菜单词条键集不一致：{set(zh) ^ set(en)}"
