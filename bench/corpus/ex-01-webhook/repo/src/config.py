import os


def get_secret(name: str) -> str:
    """All secrets come from the environment (injected by the deploy system). Never from files."""
    return os.environ[name]
