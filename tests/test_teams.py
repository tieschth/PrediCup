from bot.teams import canonical, resolve


def test_resolve_by_code():
    assert resolve(code="BRA").ru == "Бразилия"
    assert resolve(code="bra").code == "BRA"


def test_resolve_by_name_variants():
    assert resolve(name="South Korea").code == "KOR"
    assert resolve(name="Korea Republic").code == "KOR"
    assert resolve(name="Bosnia & Herzegovina").code == "BIH"
    assert resolve(name="Bosnia and Herzegovina").code == "BIH"
    assert resolve(name="IR Iran").code == "IRN"
    assert resolve(name="Côte d'Ivoire").code == "CIV"
    assert resolve(name="Ivory Coast").code == "CIV"


def test_canonical_localizes():
    assert canonical("IR Iran", "") == ("Иран", "IRN")
    assert canonical("Spain", "ESP") == ("Испания", "ESP")


def test_canonical_passthrough_unknown():
    assert canonical("Atlantis", "ATL") == ("Atlantis", "ATL")
