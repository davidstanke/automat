from app.tools import MOCK_MENUS, get_catering_menus


def test_mock_menus_structure() -> None:
    assert len(MOCK_MENUS) == 3
    menu_ids = [m["menu_id"] for m in MOCK_MENUS]
    assert menu_ids == ["menu_1", "menu_2", "menu_3"]

    # Check Menu 1
    m1 = MOCK_MENUS[0]
    assert m1["name"] == "Buffalo Chicken Wrap"
    assert m1["items"] == [
        "buffalo chicken wrap",
        "mixed greens salad",
        "chocolate cookie",
        "assorted sodas",
    ]

    # Check Menu 2
    m2 = MOCK_MENUS[1]
    assert m2["name"] == "Veggie Tacos"
    assert m2["items"] == [
        "veggie tacos",
        "snow pea salad",
        "apple tartlets",
        "tea service",
    ]

    # Check Menu 3
    m3 = MOCK_MENUS[2]
    assert m3["name"] == "Lamb Vindaloo"
    assert m3["items"] == [
        "lamb vindaloo",
        "spiced cauliflower",
        "naan",
        "orange-mint spa water",
    ]


def test_get_catering_menus() -> None:
    result = get_catering_menus()
    assert "### Catering Menu Options" in result
    assert "Buffalo Chicken Wrap" in result
    assert "Veggie Tacos" in result
    assert "Lamb Vindaloo" in result
    assert "menu_1" in result
    assert "menu_2" in result
    assert "menu_3" in result
