"""
Static checks on the web client. There is no browser test setup, so these pin
regressions by reading the shipped JS and CSS.
"""
import os
import re

WEB = os.path.join(os.path.dirname(__file__), "..", "web")


def _read(*parts: str) -> str:
    with open(os.path.join(WEB, *parts), encoding="utf-8") as f:
        return f.read()


def test_pass_button_is_shown_with_an_explicit_display_value():
    """The stylesheet hides #pass-btn by default, so clearing the inline style
    (display = '') leaves it hidden. Showing it needs a real display value."""
    css = _read("src", "styles", "table.css")
    js = _read("src", "pages", "game.js")

    hidden_by_default = re.search(r"#pass-btn\s*\{[^}]*display:\s*none", css) is not None
    shown = re.search(
        r"getElementById\('pass-btn'\)\.style\.display\s*=\s*hasPass\s*\?\s*'([^']*)'", js)

    assert shown, "game.js no longer toggles #pass-btn the way this test expects"
    if hidden_by_default:
        assert shown.group(1) not in ("", "none"), (
            "pass button can never appear: table.css hides it and game.js only "
            "clears the inline style")
