from app.tools import get_catering_menus, MOCK_MENUS


def test_get_catering_menus_returns_three_menus() -> None:
    menus = get_catering_menus()
    assert isinstance(menus, list)
    assert len(menus) == 3


def test_get_catering_menus_conforms_to_schema() -> None:
    menus = get_catering_menus()
    menu_ids = [m["menu_id"] for m in menus]
    assert menu_ids == ["menu_1", "menu_2", "menu_3"]

    expected_names = ["Buffalo Chicken Wrap", "Veggie Tacos", "Lamb Vindaloo"]
    for i, menu in enumerate(menus):
        assert menu["name"] == expected_names[i]
        assert isinstance(menu["items"], list)
        assert len(menu["items"]) == 4

    # Option 1 items check
    assert menus[0]["items"] == [
        "buffalo chicken wrap",
        "mixed greens salad",
        "chocolate cookie",
        "assorted sodas",
    ]

    # Option 2 items check
    assert menus[1]["items"] == [
        "veggie tacos",
        "snow pea salad",
        "apple tartlets",
        "tea service",
    ]

    # Option 3 items check
    assert menus[2]["items"] == [
        "lamb vindaloo",
        "spiced cauliflower",
        "naan",
        "orange-mint spa water",
    ]
