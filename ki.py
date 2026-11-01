# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo-studio==0.4.0",
#     "sandlock>=0.9.0",
# ]
# ///

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from typing import NoReturn, cast

from sandlock import Sandbox
from dataclasses import dataclass
from pathlib import Path

IS_DAPLA_ENVIRONMENT = "DAPLA_ENVIRONMENT" in os.environ
MARIMO_ADRESS = f"http://localhost:{8080 if IS_DAPLA_ENVIRONMENT else 2718}"


@dataclass
class Arguments:
    dry_run: bool


def parse_args() -> Arguments:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return Arguments(dry_run=args.dry_run)


@dataclass
class Source:
    path: Path
    usage: str


@dataclass
class AgentSession:
    sources: list[Source]
    instructions: list[str]
    context: str
    initial_prompt: str
    writeable_directory: Path


def main() -> None:
    arguments = parse_args()
    notebook_file = find_active_notebook()
    view = get_view(notebook_file)
    html_file = view.joinpath("index.html")

    sources = get_sources()
    instructions = get_intructions(sources)
    context = generate_context(notebook_file, html_file)

    print("Aktive Marimo-filer")
    print(f"  Notebook: {notebook_file}")
    print(f"  View:     {html_file}")
    print()
    print("Kilder lastet")
    for source in sources:
        print(f"    {source.path}")
    print()
    print("Relevant kontekst er lastet.")
    print(
        "Husk at det er lurt å installere relevante Python-pakker i notebooken, da får agenten rask tilgang til relevant pakkedokumentasjon."
    )
    print(
        "Skriv inn hva du ønsker skal gjøres og trykk deretter Enter for å starte agenten (eller Ctrl+C for å avbryte)."
    )
    print()

    initial_prompt = input("> ")
    agent_session = AgentSession(
        sources, instructions, context, initial_prompt, notebook_file.parent
    )
    if arguments.dry_run:
        print(build_prompt(agent_session))
    else:
        start_agent(agent_session)

def build_prompt(agent_session: AgentSession) -> str:
    prompt = "# Instructions\n\n"
    prompt += "\n".join(
        f"- {instruction}" for instruction in agent_session.instructions
    )
    prompt += f"\n\n# Context\n\n{agent_session.context}"
    prompt += f"\n\n# User request\n\n{agent_session.initial_prompt}"
    return prompt


def start_agent(agent_session: AgentSession) -> None:
    sandbox = Sandbox(
        fs_readable=[str(Path.home())],
        fs_writable=[str(agent_session.writeable_directory)],
        cwd=str(agent_session.writeable_directory),
        net_allow=[],
    )
    exit_code = sandbox.run_interactive(
        ["opencode", "--prompt", build_prompt(agent_session)]
    )
    if exit_code != 0:
        raise subprocess.CalledProcessError(exit_code, "opencode")

def get_sources() -> list[Source]:
    dapla_manual = fetch_github_docs(
        "statisticsnorway/dapla-manual", "dapla-manual/statistikkere"
    )
    designsystemet = fetch_github_docs("digdir/designsystemet", "apps/www/app/content")
    marimo_notebook = Path.home() / ".agents" / "skills" / "marimo-notebook"
    marimo_pair = Path.home() / ".agents" / "skills" / "marimo-pair"
    notebook_python_packages = get_notebook_site_packages(notebook_file)
    return [
        Source(
            dapla_manual,
            "Always read relevant documentation from here before developing anything.",
        ),
        Source(
            designsystemet,
            "Read relevant documentation from here before developing the html view.",
        ),
        Source(marimo_notebook, "Read this skill before developing the notebook."),
        Source(marimo_pair, "Read this skill before developing the notebook."),
        Source(
            Path(notebook_python_packages),
            "Always read relevant API documentation here before using packages.",
        ),
    ]


def get_intructions(sources: list[Source]) -> list[str]:
    instructions = [
        "Develop the reactive Marimo application and its Marimo Studio html view.",
        "In general you should only use the marimo-pair execute-code script for developing the notebook. Direct writes to the notebook  only be done for small fixes and verified with `uv run marimo check APP_FILE`.", #TODO replace with actual app name
        "Use English for code and Norwegian for output.",
        "Avoid implementing large amounts of logic and data-processing; prefer a thin layer over excisting SSB packages.",
        "",
    ]
    instructions.extend(f"{source.usage} Path: {source.path}" for source in sources)
    return instructions


def generate_context(app_file: Path, html_file: Path) -> str:
    return f"""## Current Marimo notebook ({app_file})

{app_file.read_text(encoding="utf-8")}

## Current HTML view ({html_file})

{html_file.read_text(encoding="utf-8")}
"""




# TODO leave function as is for reference
def generate_notebook_context(arguments: Arguments, app_file: Path) -> str:
    app_file = app_file.resolve()
    dapla_manual_docs_path = fetch_github_docs(
        "statisticsnorway/dapla-manual", "dapla-manual/statistikkere"
    )
    return f'''\
# Context

I want help developing a reactive Marimo application in {app_file}.

## The Marimo Python API for editing a Marimo notebook

Result of `import marimo._code_mode as cm; help(cm)`:

{get_marimo_python_api_docs(app_file)}

## Instructions and prompt

Use the marimo-notebook skill to understand Marimo concepts.
Note especially that outputs must be assigned to variables and used as the final expression of the cell.

Use the marimo-pair skill to develop the notebook.
When adding an editing cells, only insert the content, not marimo cell decorators/functions.
You do not have to run the setup commands, the notebook is already connected:

bash ~/.agents/skills/marimo-pair/scripts/execute-code.sh --url "{MARIMO_ADRESS}" --file "{app_file}"

Before every change, you **must** first explain the change to me.
Prefer running the command as few times as possible to avoid overwhelming me with requests.
Avoid extensive testing - I will test the app myself and provide feedback.
Do **not** run other shell commands.
Do **not** edit the notebook directly.

Before using packages, always read the relevant package APIs directly from the source: {get_notebook_site_packages(app_file)}.
Do not use the **shell** tool for this; use the glob, grep and read tools in the folder.

Use English for code and Norwegian for output.
Do not write large amounts of logic or data processing - prefer a thin interactive layer over existing SSB packages.
Do not write large amounts of html and css, and do not include headers or other static content.
Prefer having outputs in separate cells instead of combining them into stacks.
Every cell **must** be given a meaningful name.

Start by using the skill tool to load marimo-notebook and marimo-pair.
Then read relevant package documentation directly from the source, including the Marimo UI component APIs.
Read relevant statistikkere documentation from {dapla_manual_docs_path}. 
Then use the question tool to clarify requirements based on your findings.

Main prompt (respond in the same language):

*{arguments.prompt}*

    '''


# TODO leave function as is for reference
def generate_design_context(arguments: Arguments, app_file: Path) -> str:
    app_file = app_file.resolve()
    designsystemet_docs_path = fetch_github_docs(
        "digdir/designsystemet", "apps/www/app/content"
    )
    dapla_manual_docs_path = fetch_github_docs(
        "statisticsnorway/dapla-manual", "dapla-manual/statistikkere"
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
Also read the relevant documentation for statistikkere from {dapla_manual_docs_path}.
Then use the question tool to clarify requirements based on your findings.

Main prompt (respond in the same language):

*{arguments.prompt}*

    """


def exit_because_notebook_session_is_not_active() -> NoReturn:
    print("Notebook-filen må være åpen i Marimo-grensesnittet.", file=sys.stderr)
    raise SystemExit(1)


def find_active_notebook() -> Path:
    try:
        with urllib.request.urlopen(
            f"{MARIMO_ADRESS}/api/sessions", timeout=2
        ) as response:
            sessions = json.load(response)
    except Exception:
        exit_because_notebook_session_is_not_active()

    if not isinstance(sessions, dict):
        exit_because_notebook_session_is_not_active()

    first = next(iter(sessions.values()), None)
    path = first.get("path") if isinstance(first, dict) else None
    if not isinstance(path, str) or not Path(path).is_file():
        exit_because_notebook_session_is_not_active()
    return Path(path)


def run_in_marimo_session(app_file: Path, code: str) -> str:
    command = [
        "bash",
        os.path.expanduser("~/.agents/skills/marimo-pair/scripts/execute-code.sh"),
        "--url",
        MARIMO_ADRESS,
        "--file",
        str(app_file),
        "-c",
        code,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        exit_because_notebook_session_is_not_active()
    return result.stdout


def get_notebook_site_packages(app_file: Path) -> str:
    return run_in_marimo_session(
        app_file,
        "import sysconfig; print(sysconfig.get_path('purelib'))",
    ).strip()


def get_marimo_python_api_docs(app_file: Path) -> str:
    return run_in_marimo_session(app_file, "import marimo._code_mode as cm; help(cm)")


def get_view(app_file: Path) -> Path:
    return asyncio.run(_get_view(app_file))


async def _get_view(app_file: Path) -> Path:
    from marimo_studio.authoring import open_workspace

    workspace = open_workspace(app_file)
    overview = await workspace.status()

    if (
        overview.default_view is not None
        and (overview.view_root / overview.default_view).is_dir()
    ):
        view = workspace.view(overview.default_view)
        inspection = await view.inspect()
        if inspection.provider == "marimo-studio/vanilla":
            return Path(inspection.root)

    name = "dashboard"
    print(f"Oppretter nytt dashboard-view '{name}.html'...")
    view = await workspace.create_view(
        name,
        starter="marimo-studio/vanilla:default",
        make_default=True,
    )

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
    print(f"Fetching relevant docs: {repo_name}")
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
