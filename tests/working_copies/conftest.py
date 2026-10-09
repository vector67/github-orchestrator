import pytest

from tests.working_copies.support import real_working_copies


@pytest.fixture
def copies(settings):
    return real_working_copies(settings)
