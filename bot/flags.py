"""Преобразование кода сборной в эмодзи-флаг.

Провайдеры отдают трёхбуквенные коды (FIFA/TLA), которые часто не совпадают с
ISO-3166. Держим маппинг FIFA -> ISO alpha-2 и собираем флаг из regional
indicator symbols. Для неизвестных кодов — нейтральный значок.
"""
from __future__ import annotations

# FIFA/TLA код -> ISO 3166-1 alpha-2 (для эмодзи-флага).
# Покрывает вероятных участников ЧМ-2026 и крупные сборные; пополняемо.
_FIFA_TO_ISO: dict[str, str] = {
    "ARG": "AR", "AUS": "AU", "AUT": "AT", "BEL": "BE", "BRA": "BR",
    "CAN": "CA", "CHI": "CL", "CMR": "CM", "COL": "CO",
    "CRC": "CR", "CRO": "HR", "CZE": "CZ", "DEN": "DK", "ECU": "EC",
    "EGY": "EG", "ENG": "GB", "ESP": "ES", "FRA": "FR", "GER": "DE",
    "GHA": "GH", "GRE": "GR", "IRN": "IR", "ITA": "IT", "JPN": "JP",
    "KOR": "KR", "KSA": "SA", "MAR": "MA", "MEX": "MX", "NED": "NL",
    "NGA": "NG", "NOR": "NO", "PAN": "PA", "PAR": "PY", "PER": "PE",
    "POL": "PL", "POR": "PT", "QAT": "QA", "ROU": "RO", "RSA": "ZA",
    "SCO": "GB", "SEN": "SN", "SRB": "RS", "SUI": "CH", "SWE": "SE",
    "TUN": "TN", "TUR": "TR", "UKR": "UA", "URU": "UY", "USA": "US",
    "WAL": "GB", "ALG": "DZ", "CIV": "CI", "NZL": "NZ", "JOR": "JO",
    "UZB": "UZ", "CUW": "CW", "HAI": "HT", "JAM": "JM", "HON": "HN",
    "CPV": "CV", "TRI": "TT", "SLV": "SV", "GUA": "GT",
    "BIH": "BA", "IRQ": "IQ", "COD": "CD",
}

_NEUTRAL = "🏳️"


def _iso_to_flag(iso2: str) -> str:
    iso2 = iso2.upper()
    if len(iso2) != 2 or not iso2.isalpha():
        return _NEUTRAL
    # regional indicator symbols: 'A' (0x41) -> 0x1F1E6
    return "".join(chr(0x1F1E6 + (ord(c) - ord("A"))) for c in iso2)


def flag_for_code(code: str | None) -> str:
    """Вернуть эмодзи-флаг по коду сборной. Принимает FIFA/TLA или ISO alpha-2."""
    if not code:
        return _NEUTRAL
    code = code.strip().upper()
    iso = _FIFA_TO_ISO.get(code)
    if iso:
        return _iso_to_flag(iso)
    if len(code) == 2:
        return _iso_to_flag(code)
    return _NEUTRAL
