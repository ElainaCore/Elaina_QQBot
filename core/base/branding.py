"""ElainaQQ 产品名称与公开文本处理。"""

from __future__ import annotations

from typing import Any

PRODUCT_NAME = 'ElainaQQ'


def public_text(value: Any) -> str:
    """将运行时值转换为可供日志、面板和 API 使用的文本。"""
    return str(value)
