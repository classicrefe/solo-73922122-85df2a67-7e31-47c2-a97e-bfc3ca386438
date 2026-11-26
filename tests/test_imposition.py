from app.imposition import pad_pages, saddle_stitch_positions


def test_pad_to_multiple_of_four():
    assert pad_pages(["A"]) == ["A", None, None, None]
    assert pad_pages(["A", "B", "C", "D"]) == ["A", "B", "C", "D"]
    assert pad_pages(["A", "B", "C", "D", "E"]) == [
        "A", "B", "C", "D", "E", None, None, None,
    ]


def test_saddle_stitch_8_pages():
    pages = [f"P{i}" for i in range(1, 9)]
    pos = saddle_stitch_positions(pages)
    assert pos == [
        {"front": {"left": "P8", "right": "P1"}, "back": {"left": "P2", "right": "P7"}},
        {"front": {"left": "P6", "right": "P3"}, "back": {"left": "P4", "right": "P5"}},
    ]


def test_saddle_stitch_4_pages_single_sheet():
    pos = saddle_stitch_positions(["A", "B", "C", "D"])
    assert pos == [
        {"front": {"left": "D", "right": "A"}, "back": {"left": "B", "right": "C"}}
    ]


def test_saddle_stitch_12_pages_outside_to_inside():
    pages = [f"P{i}" for i in range(1, 13)]
    pos = saddle_stitch_positions(pages)
    assert pos[0] == {
        "front": {"left": "P12", "right": "P1"},
        "back": {"left": "P2", "right": "P11"},
    }
    assert pos[2] == {
        "front": {"left": "P8", "right": "P5"},
        "back": {"left": "P6", "right": "P7"},
    }


def test_blank_padding_lands_on_expected_faces():
    pos = saddle_stitch_positions(pad_pages(["A"]))
    assert pos[0]["front"] == {"left": None, "right": "A"}
    assert pos[0]["back"] == {"left": None, "right": None}
