"""Каноническая таблица сборных ЧМ-2026.

Назначение: привести данные любого провайдера к единому виду — русское название
+ FIFA-код (для флага). Провайдеры дают команды по-разному: football-data.org —
поле tla + английское имя ("Korea Republic", "IR Iran"), openfootball — только
строку-имя без кода ("South Korea", "Bosnia & Herzegovina"). Резолвер matchит и
по коду, и по имени (с нормализацией), поэтому расхождения в написании не страшны.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Team:
    code: str  # FIFA/TLA, используется для флага (bot/flags.py)
    ru: str  # отображаемое название
    aliases: tuple[str, ...]  # английские/альтернативные написания


# 48 участников ЧМ-2026. aliases покрывают написания football-data.org и openfootball.
_TEAMS: list[Team] = [
    Team("MEX", "Мексика", ("Mexico",)),
    Team("RSA", "ЮАР", ("South Africa",)),
    Team("KOR", "Южная Корея", ("South Korea", "Korea Republic", "Korea")),
    Team("CZE", "Чехия", ("Czech Republic", "Czechia")),
    Team("CAN", "Канада", ("Canada",)),
    Team("SUI", "Швейцария", ("Switzerland",)),
    Team("QAT", "Катар", ("Qatar",)),
    Team("BIH", "Босния и Герцеговина",
         ("Bosnia & Herzegovina", "Bosnia and Herzegovina")),
    Team("BRA", "Бразилия", ("Brazil",)),
    Team("MAR", "Марокко", ("Morocco",)),
    Team("HAI", "Гаити", ("Haiti",)),
    Team("SCO", "Шотландия", ("Scotland",)),
    Team("USA", "США", ("USA", "United States", "United States of America")),
    Team("PAR", "Парагвай", ("Paraguay",)),
    Team("AUS", "Австралия", ("Australia",)),
    Team("TUR", "Турция", ("Turkey", "Türkiye", "Turkiye")),
    Team("GER", "Германия", ("Germany",)),
    Team("CUW", "Кюрасао", ("Curacao", "Curaçao")),
    Team("CIV", "Кот-д’Ивуар", ("Cote d'Ivoire", "Côte d'Ivoire", "Ivory Coast")),
    Team("ECU", "Эквадор", ("Ecuador",)),
    Team("NED", "Нидерланды", ("Netherlands", "Holland")),
    Team("JPN", "Япония", ("Japan",)),
    Team("TUN", "Тунис", ("Tunisia",)),
    Team("SWE", "Швеция", ("Sweden",)),
    Team("BEL", "Бельгия", ("Belgium",)),
    Team("EGY", "Египет", ("Egypt",)),
    Team("IRN", "Иран", ("Iran", "IR Iran")),
    Team("NZL", "Новая Зеландия", ("New Zealand",)),
    Team("ESP", "Испания", ("Spain",)),
    Team("CPV", "Кабо-Верде", ("Cabo Verde", "Cape Verde")),
    Team("KSA", "Саудовская Аравия", ("Saudi Arabia",)),
    Team("URU", "Уругвай", ("Uruguay",)),
    Team("FRA", "Франция", ("France",)),
    Team("SEN", "Сенегал", ("Senegal",)),
    Team("NOR", "Норвегия", ("Norway",)),
    Team("IRQ", "Ирак", ("Iraq",)),
    Team("ARG", "Аргентина", ("Argentina",)),
    Team("ALG", "Алжир", ("Algeria",)),
    Team("AUT", "Австрия", ("Austria",)),
    Team("JOR", "Иордания", ("Jordan",)),
    Team("POR", "Португалия", ("Portugal",)),
    Team("COL", "Колумбия", ("Colombia",)),
    Team("UZB", "Узбекистан", ("Uzbekistan",)),
    Team("COD", "ДР Конго",
         ("DR Congo", "Congo DR", "Democratic Republic of the Congo",
          "Congo Democratic Republic")),
    Team("ENG", "Англия", ("England",)),
    Team("CRO", "Хорватия", ("Croatia",)),
    Team("GHA", "Гана", ("Ghana",)),
    Team("PAN", "Панама", ("Panama",)),
]


def _normalize(name: str) -> str:
    """Снять акценты, привести '&'→'and', убрать всё кроме букв/цифр, в нижний регистр."""
    name = name.replace("&", " and ")
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in name.lower() if ch.isalnum())


_BY_CODE: dict[str, Team] = {t.code: t for t in _TEAMS}
_BY_NAME: dict[str, Team] = {}
for _t in _TEAMS:
    _BY_NAME[_normalize(_t.ru)] = _t
    for _a in _t.aliases:
        _BY_NAME[_normalize(_a)] = _t


def resolve(name: str | None = None, code: str | None = None) -> Team | None:
    """Найти команду по коду (приоритет) или по имени с нормализацией."""
    if code:
        t = _BY_CODE.get(code.strip().upper())
        if t:
            return t
    if name:
        t = _BY_NAME.get(_normalize(name))
        if t:
            return t
    return None


def canonical(name: str, code: str = "") -> tuple[str, str]:
    """Вернуть (русское_название, FIFA_код). Если команда не распознана —
    вернуть исходные значения как есть (бот не падает, просто без локализации)."""
    t = resolve(name=name, code=code)
    if t:
        return t.ru, t.code
    return name, code
