from __future__ import annotations

import pytest

from taskcontroller.errors import TaskControllerValidationError
from taskcontroller.interaction.github_rest_transport import GitHubRestConfig


def test_github_rest_default_origin_is_trusted() -> None:
    config = GitHubRestConfig()
    assert config.api_url == "https://api.github.com"
    assert config.trusted_hosts == ("api.github.com",)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.github.com",
        "https://attacker.example",
        "https://user:pass@api.github.com",
        "https://api.github.com?token=leak",
        "https://api.github.com#fragment",
    ],
)
def test_github_rest_rejects_untrusted_or_credential_bearing_api_urls(url: str) -> None:
    with pytest.raises(TaskControllerValidationError):
        GitHubRestConfig(api_url=url)


def test_github_enterprise_requires_explicit_trusted_host_allowlist() -> None:
    config = GitHubRestConfig(
        api_url="https://github.example.bank/api/v3",
        trusted_hosts=("github.example.bank",),
    )
    assert config.api_url == "https://github.example.bank/api/v3"
