from pr_summary.settings import Settings, kind_of, settings_from, ticket_key


def test_defaults_apply_when_there_is_no_config() -> None:
    assert settings_from(None) == Settings()


def test_a_config_table_replaces_only_the_keys_it_names() -> None:
    settings = settings_from('[pr_summary]\ntests = ["spec/**"]\nwhy_guidance = "Decisions live in the wiki."\n')

    assert settings.tests == ("spec/**",)
    assert settings.why_guidance == "Decisions live in the wiki."
    assert settings.docs == Settings().docs


def test_a_config_without_the_table_is_the_defaults() -> None:
    assert settings_from('[other]\nkey = 1\n') == Settings()


def test_the_ticket_key_comes_from_the_first_source_that_has_one() -> None:
    settings = Settings()

    assert ticket_key(settings, title="[ABC-12] Hide the button", branch="feature/XYZ-9-hide") == "ABC-12"
    assert ticket_key(settings, title="Hide the button", branch="feature/XYZ-9-hide") == "XYZ-9"


def test_ticket_sources_set_the_order() -> None:
    settings = settings_from('[pr_summary]\nticket_sources = ["branch"]\n')

    assert ticket_key(settings, title="[ABC-12] Hide", branch="main-fix") is None


def test_no_ticket_key_is_none() -> None:
    assert ticket_key(Settings(), title="Hide the export button", branch="hide-button") is None


def test_files_sort_into_ignored_docs_tests_and_production() -> None:
    settings = Settings()

    assert kind_of("uv.lock", settings) == "ignored"
    assert kind_of("frontend/package-lock.json", settings) == "ignored"
    assert kind_of("README.md", settings) == "docs"
    assert kind_of("docs/guide/setup.txt", settings) == "docs"
    assert kind_of("tests/export/test_rows.py", settings) == "tests"
    assert kind_of("src/export/test_rows.py", settings) == "tests"
    assert kind_of("app/components/row.test.ts", settings) == "tests"
    assert kind_of("src/export/rows.py", settings) == "production"


def test_markdown_inside_a_test_folder_is_docs() -> None:
    assert kind_of("tests/README.md", Settings()) == "docs"


def test_ticket_projects_rule_out_keys_from_other_projects() -> None:
    settings = settings_from('[pr_summary]\nticket_projects = ["ABC"]\n')

    assert ticket_key(settings, title="Use UTF-8 for ABC-7 exports", branch="x") == "ABC-7"
    assert ticket_key(settings, title="Use UTF-8 everywhere", branch="x") is None


def test_author_prose_outside_markdown_is_docs() -> None:
    settings = Settings()

    assert kind_of("README", settings) == "docs"
    assert kind_of("CHANGELOG.txt", settings) == "docs"
    assert kind_of("packages/api/docs/setup.html", settings) == "docs"
    assert kind_of("guide.adoc", settings) == "docs"
    assert kind_of("notebooks/explore.ipynb", settings) == "docs"
