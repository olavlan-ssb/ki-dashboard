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
    html_file = view.joinpath("index.html")
    return f'''\
# Context

I want help developing a Marimo Studio view on top of my Marimo application {app_file}.
The view is a plain html file: {html_file}.

## The current Marimo notebook content

{app_file.read_text(encoding="utf-8")}

## The current view content

{html_file.read_text(encoding="utf-8")}

## How Marimo Studio views work  

TODO insert marimo studio agent skill documentation here

## Instructions and prompt

You should **not** edit the Marimo notebook.
Your job is to develop the layout on top of the notebook according to my prompt. 
Your should **only** to make edits to {html_file}.
Refer the user to the `ki` terminal command for notebook changes.

You must **never** remove the style block that has the designsystemet imports.
This sets the styling for the Marimo UI components.
There is no proper way to further adjust the styling of the Marimo UI components. 
Focus on the overall styling of the page and laying out the cells.

You should **always** try to use designsystemet layout components and design tokens.
Start your process by reading relevant documentation here: https://github.com/digdir/designsystemet/tree/main/apps/www/app/content. 
Then use the question tool to clarify my requirements based on your findings.

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
   
    # if the notebook has a connected html view, use that
    if overview.default_view is not None:
        view = workspace.view(overview.default_view)
        inspection = await view.inspect()
        if inspection.provider == "marimo-studio/vanilla":
            return Path(inspection.root)

    # if not, create a new html view "ssb.html" and make it default 
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

    # inject ssb styling in the new document
    document = await view.read("index.html")
    if "</head>" in document.content:
        content = document.content.replace(
            "</head>",
            f"{get_ssb_style_block()}\n</head>",
            1,
        )
        await view.write("index.html", content, expected_revision=document.revision)

    return Path((await view.inspect()).root)


def get_ssb_style_block() -> str:
    return """\
<style>
@import url("https://cdn.jsdelivr.net/npm/@digdir/designsystemet-css@1.23.0/dist/src/index.css");
@import url("https://cdn.jsdelivr.net/npm/@statisticsnorway/design-css@0.2.4/dist/src/fonts/fonts.css");
@import url("https://cdn.jsdelivr.net/npm/@statisticsnorway/design-css@0.2.4/dist/theme/ssb.css");

:root {
  --marimo-cell-font: var(--ds-font-family);
  --marimo-cell-heading-font: var(--ds-font-family);
  --marimo-cell-background: var(--ds-color-background-default);
  --marimo-cell-foreground: var(--ds-color-text-default);
  --marimo-cell-surface: var(--ds-color-surface-default);
  --marimo-cell-border-color: var(--ds-color-border-subtle);
  --marimo-cell-accent: var(--ds-color-base-default);
  --marimo-cell-error: var(--ds-color-base-default);
  --marimo-cell-radius: var(--ds-border-radius-default);
  --marimo-cell-padding: var(--ds-size-4);
}
</style>"""


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
