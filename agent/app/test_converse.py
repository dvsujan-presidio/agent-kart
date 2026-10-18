from app.converse import render

PH = {"total": "₹2,665", "late_day": "Tuesday", "opt1_title": "drop banner", "stores": "2"}


def test_placeholders_with_underscores_render():
    out = render(
        "Plan is {total} from {stores} stores; the cheaper cups arrive {late_day}. Try {opt1_title}?",
        PH,
    )
    assert out == "Plan is ₹2,665 from 2 stores; the cheaper cups arrive Tuesday. Try drop banner?"


def test_model_written_numbers_are_rejected():
    assert render("That is 2665 rupees in total", PH) is None
    assert render("About two hundred rupees left", PH) is None
    assert render("Total {total}, delivery in 2 days", PH) is None


def test_unknown_placeholder_rejected_and_markdown_stripped():
    assert render("Total {nope}", PH) is None
    assert render("**Total** is {total}", PH) == "Total is ₹2,665"
