"""插件公开接口所需的运行时绑定。"""

from typing import Any

_application: Any = None


def bind_application(application: Any) -> None:
    """由应用装配层绑定或释放当前实例。"""
    global _application
    _application = application


def get_application():
    return _application
