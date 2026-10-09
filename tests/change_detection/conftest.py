import pytest

from tests.change_detection.support import fake_change_detection


@pytest.fixture
def detection():
    return fake_change_detection()
