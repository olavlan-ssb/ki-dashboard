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
from dataclasses import dataclass
from pathlib import Path

IS_DAPLA_ENVIRONMENT = "DAPLA_ENVIRONMENT" in os.environ
MARIMO_ADRESS = f"http://localhost:{8080 if IS_DAPLA_ENVIRONMENT else 2718}"


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
        return

    subprocess.run(
        ["opencode", "--prompt", context],
        check=True,
    )


def generate_context(arguments: Arguments) -> str:
    app_file = arguments.app_file.resolve()
    designsystemet_docs_path = fetch_github_docs(
        "digdir/designsystemet", "apps/www/app/content"
    )
    view = get_view(app_file)
    html_file = view.joinpath("index.html")
    return f"""\
# Context

I want help developing a Marimo Studio view on top of my Marimo application {app_file}.
The view is a plain html file: {html_file}.

## The current Marimo notebook content

{app_file.read_text(encoding="utf-8")}

## The current view content

{html_file.read_text(encoding="utf-8")}

## Instructions and prompt

Your job is to develop a html view on top of the notebook.
Your should only make edits to {html_file}.
You should not edit the Marimo notebook, but read it to ensure that the cells are inserted correctly in the html.

Do not remove Marimo-specific javascript code.
Do not remove the style block that has the designsystemet imports.
This sets the styling for the Marimo UI components.
There is no way to further adjust the styling of the Marimo UI components.

Always prefer using designsystemet layout components when possible.
Avoid using hardcoded style values - use designsystemet design tokens instead.
In particular, you do not need to hardcode anything to get SSB (Statistisk sentralbyrå) theme.

Start by reading relevant designsystemet docs from {designsystemet_docs_path}. 
Then use the question tool to clarify requirements based on your findings.

Main prompt (respond in the same language):

*{arguments.prompt}*

    """


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
        parser.error(
            "det andre argumentet må være en kort beskrivelse av ønsket layout"
        )
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
    print("Finner eksisterende view...")
    if (
        overview.default_view is not None
        and (overview.view_root / overview.default_view).is_dir()
    ):
        view = workspace.view(overview.default_view)
        inspection = await view.inspect()
        if inspection.provider == "marimo-studio/vanilla":
            return Path(inspection.root)

    # if not, create a new html view "dashboard.html" and make it default
    name = "dashboard"
    print(f"Oppretter nytt dashboard-view '{name}.html'...")
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
    await view.build()
    return Path((await view.inspect()).root)





def get_ssb_style_block() -> str:
    return """\
<!-- Do not remove this style block. -->
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


def fetch_github_docs(repo_name: str, docs_path: str) -> Path:
    destination = Path.home() / ".cache" / repo_name
    if destination.is_dir():
        return destination
    print("Fetching relevant docs..")
    destination.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as temporary:
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--filter=blob:none",
                "--sparse",
                f"https://github.com/{repo_name}.git",
                temporary,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["git", "-C", temporary, "sparse-checkout", "set", docs_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.copytree(Path(temporary) / docs_path, destination, dirs_exist_ok=True)
    return destination


if __name__ == "__main__":
    main()
