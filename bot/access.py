"""Проверки прав доступа на основе ролей из конфига.

Сейчас одна роль — admin. Расширяемо: достаточно добавить новые списки в
RolesCfg и хелперы здесь, не трогая хендлеры по существу.
"""
from __future__ import annotations

from bot.config import Settings


def is_admin(settings: Settings, user_id: int) -> bool:
    return user_id in settings.app.roles.admins
