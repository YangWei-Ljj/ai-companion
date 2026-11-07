"""人设预设库：从 presets/presets.json 加载，默认人设不再硬编码在代码里。"""
from __future__ import annotations

import json

from . import config

DEFAULT_PRESETS = [
    {
        "id": "gentle",
        "name": "温柔闺蜜",
        "nick_name": "小柔",
        "nature": "温柔体贴、善解人意，说话轻声细语，喜欢鼓励和陪伴对方",
    },
    {
        "id": "lively",
        "name": "活泼少女",
        "nick_name": "锦锦",
        "nature": "美丽漂亮和活泼开朗的丽水姑娘，爱撒娇、爱用可爱的 emoji，聊天轻松有趣",
    },
    {
        "id": "rational",
        "name": "知性姐姐",
        "nick_name": "知秋",
        "nature": "知性成熟、理性冷静，能聊工作学习，也会在你低落时给出靠谱建议",
    },
]


def load_presets() -> list[dict]:
    preset_file = config.PRESET_DIR / "presets.json"
    if not preset_file.exists():
        return DEFAULT_PRESETS
    try:
        data = json.loads(preset_file.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_PRESETS


def get_preset(preset_id: str | None) -> dict | None:
    if not preset_id:
        return None
    for p in load_presets():
        if p.get("id") == preset_id:
            return p
    return None
