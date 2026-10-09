import os

import pytest

from github_orchestrator.settings.fake import fake_settings
from github_orchestrator.wiring import (
    board_font_dir,
)


@pytest.mark.parametrize(("configured", "expected"), [
    ("~/design/fonts", os.path.expanduser("~/design/fonts")),
    ("", None),
])
def test_the_board_is_built_with_the_configured_font_directory(tmp_path, configured, expected):
    assert board_font_dir(fake_settings(tmp_path, board_font_dir=configured)) == expected
