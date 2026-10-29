# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo-studio==0.4.0",
# ]
# ///

import argparse
import asyncio
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path

MARIMO_SERVER_PORT = 2718

@dataclass
class Arguments:
    dry_run: bool
    app_file: Path
    prompt: str

def main() -> None:
    arguments = parse_args()
    context = generate_context(arguments)

    if arguments.dry_run:
        print(context)
    else:
        subprocess.run(["opencode", "mini", "--prompt", context], check=True)


def generate_context(arguments: Arguments) -> str:
    app_file = arguments.app_file.resolve()
    view = get_view(app_file)
    return f'''\
# Context

I want help developing a Marimo studio view on top of my Marimo application {app_file}.
The view is a plain html file in {view}.

## The current Marimo notebook content

{app_file.read_text(encoding="utf-8")}

## The current view content

{view.joinpath("index.html").read_text(encoding="utf-8")}

## Instructions and prompt

Main prompt (respond in the same language):

*{arguments.prompt}*

    '''



def parse_args() -> Arguments:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("app_file", type=Path, nargs="?")
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()
    if args.app_file is None:
        parser.error("det første argumentet må være en eksisterende Marimo-fil")
    if not args.app_file.is_file():
        parser.error(f"Marimo-filen finnes ikke: {args.app_file}")
    if args.prompt is None:
        parser.error("det andre argumentet må være en kort beskrivelse av ønsket layout")
    return Arguments(
        dry_run=args.dry_run,
        app_file=args.app_file,
        prompt=args.prompt,
    )


def get_view(app_file: Path) -> Path:
    return asyncio.run(_get_view(app_file))


async def _get_view(app_file: Path) -> Path:
    from marimo_studio.authoring import open_workspace

    workspace = open_workspace(app_file)
    overview = await workspace.status()
    
    if overview.default_view is not None:
        view = workspace.view(overview.default_view)
        inspection = await view.inspect()
        if inspection.provider == "marimo-studio/vanilla":
            return Path(inspection.root)

    name = "ssb"
    names = set(overview.views)
    suffix = 2
    while name in names:
        name = f"ssb-{suffix}"
        suffix += 1

    view = await workspace.create_view(
        name,
        starter="marimo-studio/vanilla:default",
        make_default=True,
    )
    return Path((await view.inspect()).root)

def exit_because_notebook_session_is_not_active(app_file: Path) -> None:
    print(f"Filen '{app_file}' må være åpnet i Marimo-grensesnittet", file=sys.stderr)
    raise SystemExit(1)



def get_notebook_environment(app_file: Path) -> str:
    result = subprocess.run(
        ["uv", "python", "find", "--script", str(app_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        exit_because_notebook_session_is_not_active(app_file)
    return result.stdout.strip()


if __name__ == "__main__":
    main()
