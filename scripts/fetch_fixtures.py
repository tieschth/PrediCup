"""Сухой прогон провайдера: вытащить расписание и показать, в каком виде
приходят команды (названия, коды, время), без запуска бота и без постинга.

Запуск (из корня проекта, в активированном venv):
    python scripts/fetch_fixtures.py            # все матчи
    python scripts/fetch_fixtures.py 12         # только первые 12 по времени

Провайдер берётся из config.yaml (provider.name). Чтобы проверить боевой
источник, временно поставь provider.name: football_data_org и заполни
FOOTBALL_API_KEY в .env.
"""
from __future__ import annotations

import asyncio
import sys
from zoneinfo import ZoneInfo

from bot.config import load_settings
from bot.flags import flag_for_code
from bot.services.football.factory import build_provider

_NEUTRAL = "🏳️"


async def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    settings = load_settings()
    tz = ZoneInfo(settings.app.bot.display_timezone)
    provider = build_provider(settings)
    print(f"Провайдер: {settings.app.provider.name}")
    try:
        fixtures = await provider.fixtures()
    finally:
        await provider.close()

    fixtures.sort(key=lambda f: f.kickoff_utc)
    if limit:
        fixtures = fixtures[:limit]

    print(f"Всего матчей: {len(fixtures)}\n")
    missing: set[str] = set()
    for f in fixtures:
        hf, af = flag_for_code(f.home_code), flag_for_code(f.away_code)
        if hf == _NEUTRAL:
            missing.add(f"{f.home_team!r} (код {f.home_code!r})")
        if af == _NEUTRAL:
            missing.add(f"{f.away_team!r} (код {f.away_code!r})")
        local = f.kickoff_utc.astimezone(tz).strftime("%d.%m %H:%M")
        print(
            f"  [{f.provider_match_id}] {hf} {f.home_team} ({f.home_code}) "
            f"vs {f.away_team} ({f.away_code}) {af}"
            f"  | {local} {tz.key} | {f.status} | {f.stage}"
        )

    if missing:
        print("\n⚠️ Команды без флага (нужно добавить код в bot/flags.py):")
        for m in sorted(missing):
            print(f"   - {m}")
    else:
        print("\n✅ Для всех команд флаг определился.")


if __name__ == "__main__":
    asyncio.run(main())
