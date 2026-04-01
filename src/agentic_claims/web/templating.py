"""Jinja2 templates instance shared across the web package."""

from pathlib import Path

from starlette.templating import Jinja2Templates

projectRoot = Path(__file__).resolve().parent.parent.parent.parent
templates = Jinja2Templates(directory=str(projectRoot / "templates"))
