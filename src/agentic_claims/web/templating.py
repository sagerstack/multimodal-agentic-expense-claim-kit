"""Jinja2 templates instance shared across the web package."""

from pathlib import Path

from starlette.templating import Jinja2Templates


def _findProjectRoot() -> Path:
    """Find the project root containing templates/ directory."""
    candidate = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "templates").is_dir():
            return candidate
    docker = Path("/app")
    if (docker / "templates").is_dir():
        return docker
    return Path.cwd()


projectRoot = _findProjectRoot()
templates = Jinja2Templates(directory=str(projectRoot / "templates"))
