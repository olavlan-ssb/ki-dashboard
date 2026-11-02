# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo-studio==0.4.0",
#     "sandlock>=0.9.0",
# ]
# ///

import argparse
import asyncio
import curses
import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from sandlock import Sandbox

IS_DAPLA_ENVIRONMENT = "DAPLA_ENVIRONMENT" in os.environ
MARIMO_ADDRESS = f"http://localhost:{8080 if IS_DAPLA_ENVIRONMENT else 2718}"

GREEN_TEXT_START = "\033[32m"
GREEN_TEXT_STOP = "\033[39m"
ITALIC_TEXT_START = "\033[3m"
ITALIC_TEXT_STOP = "\033[23m"


@dataclass
class Arguments:
    dry_run: bool


def parse_args() -> Arguments:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return Arguments(dry_run=args.dry_run)


@dataclass
class Resource:
    path: Path
    usage: str


@dataclass
class AgentSession:
    resources: list[Resource]
    system_prompt: str
    initial_prompt: str
    writeable_paths: list[Path]
    working_directory: Path


def main() -> None:
    arguments = parse_args()
    if not arguments.dry_run:
        validate_github_repository()
    notebooks = find_active_notebooks()
    notebook_file = (
        exit_because_no_valid_marimo_session()
        if not notebooks
        else notebooks[0]
        if len(notebooks) == 1
        else choose_notebook(notebooks)
    )
    view = get_view(notebook_file)
    html_file = view.joinpath("index.html")

    resources = get_resources()
    system_prompt = get_system_prompt(resources, notebook_file, html_file)
    print(
        f"\nAktive Marimo-filer\n"
        f"  Notebook: {notebook_file}\n"
        f"  View:     {html_file}\n"
        f"\n"
        f"Relevant kontekst er lastet inn.\n"
        f"\n"
        f"{ITALIC_TEXT_START}Det anbefales å installere relevante Python-pakker i notebooken på forhånd, "
        f"slik at agenten får rask tilgang til pakkedokumentasjon.\n"
        f"Agenten vil endre notebooken gjennom kommandoer som kan være vanskelige å lese.\n"
        f"Når agenten er ferdig, kan du se alle endringene med kommandoen "
        f"{GREEN_TEXT_START}git diff{GREEN_TEXT_STOP}.\n"
        f"Kommandoen {GREEN_TEXT_START}git restore .{GREEN_TEXT_STOP}{ITALIC_TEXT_STOP} "
        f"kan brukes til å angre agentens endringer.\n"
        f"\n"
        f"{GREEN_TEXT_START}Skriv inn hva du ønsker å få gjort, og trykk Enter for å starte agenten (eller Ctrl+C for å avbryte).{GREEN_TEXT_STOP}\n"
    )

    initial_prompt = input(f"{GREEN_TEXT_START}> {GREEN_TEXT_STOP}")
    agent_session = AgentSession(
        resources,
        system_prompt,
        initial_prompt,
        [notebook_file, html_file],
        notebook_file.parent,
    )
    if arguments.dry_run:
        print(agent_session)
    else:
        start_agent(agent_session)


def get_provider_domain() -> str:
    return "opencode.ai"


def start_agent(agent_session: AgentSession) -> None:
    home = Path.home()
    pi_writable_path = home / ".pi" / "agent"
    marimo_servers_path = home / ".local" / "state" / "marimo" / "servers"

    sandbox = Sandbox(
        fs_readable=[
            str(home),
            "/nix/store",
            "/run",
        ],
        fs_writable=[
            *(str(path) for path in agent_session.writeable_paths),
            str(pi_writable_path),
            str(marimo_servers_path),
            "/tmp",
            "/dev/null",
        ],
        cwd=str(agent_session.working_directory),
        net_allow=[get_provider_domain(), MARIMO_ADDRESS.removeprefix("http://")],
    )
    exit_code = sandbox.run_interactive(
        [
            "pi",
            "--no-context-files",
            "--tools",
            "bash,read,edit,grep,ls",
            "--system-prompt",
            agent_session.system_prompt,
            agent_session.initial_prompt,
        ]
    )
    if exit_code != 0:
        raise subprocess.CalledProcessError(exit_code, "pi")


def get_resources() -> list[Resource]:
    notebook_python_packages: Resource = Resource(
        Path.home() / ".cache" / "uv" / "environments-v2",
        (
            "Always read relevant API documentation here before using packages. "
            "You must find the correct Python environment."
        ),
    )

    dapla_manual: Resource = Resource(
        fetch_github_docs(
            "statisticsnorway/dapla-manual", "dapla-manual/statistikkere"
        ),
        (
            "Always read relevant documentation from here before developing the notebook and using packages. "
            "It provides SSB-specific guidelines that should be followed."
        ),
    )

    designsystemet: Resource = Resource(
        fetch_github_docs("digdir/designsystemet", "apps/www/app/content"),
        (
            "Read relevant documentation from here before developing the html view. "
            "Always prefer using designsystemet components and design tokens instead of hardcoded css values. "
            "In particular, SSB theming come out of the box with the existing css imports (don't remove these)."
        ),
    )

    marimo_notebook: Resource = Resource(
        Path.home() / ".agents" / "skills" / "marimo-notebook",
        (
            "Always start by reading this skill to understand how to develop Marimo notebooks. "
            "Pay special attention to how Marimo outputs work. "
            "Summary: always put the output in a variable and use that as the last expression of the cell."
        ),
    )

    return [
        notebook_python_packages,
        dapla_manual,
        designsystemet,
        marimo_notebook,
    ]


def get_system_prompt(
    resources: list[Resource], notebook_file: Path, html_file: Path
) -> str:
    resources_text = "\n".join(
        f"  - {resource.path}: {resource.usage}" for resource in resources
    )
    return (
        f"Your job is to help develop the reactive Marimo application `{notebook_file}` "
        f"and its Marimo Studio HTML view `{html_file}`. You should not edit other files.\n"
        "Try to keep logic in the notebook and layout/styling in the HTML view.\n"
        "Always give meaningful names to cells and make sure the html view is in sync.\n"
        "Use English for code and Norwegian for user-facing output.\n"
        "Avoid implementing large amounts of logic and data processing; prefer a thin interaction layer over existing SSB packages.\n"
        "The following resources are available, with instructions for when and how to use them.\n"
        f"{resources_text}\n"
        "Do not use the shell tool to read them; only use the grep, glob and read tools.\n"
        "Based on your findings, use the question tool to clarify the user's requirements before implementing."
    )


def exit_because_no_valid_marimo_session() -> NoReturn:
    print(
        "Du må ha en Marimo-fil som er lagret i dashboards-mappa og er åpnet i Marimo-grensesnittet.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def find_active_notebooks() -> list[Path]:
    try:
        with urllib.request.urlopen(
            f"{MARIMO_ADDRESS}/api/sessions", timeout=2
        ) as response:
            sessions = json.load(response)
    except Exception:
        exit_because_no_valid_marimo_session()

    if not isinstance(sessions, dict):
        exit_because_no_valid_marimo_session()

    notebooks = [
        Path(session["path"])
        for session in sessions.values()
        if isinstance(session, dict)
        and isinstance(session.get("path"), str)
        and Path(session["path"]).is_file()
        and Path(session["path"]).parent.name == "dashboards"
    ]
    return notebooks


def get_view(notebook_file: Path) -> Path:
    return asyncio.run(_get_view(notebook_file))


async def _get_view(notebook_file: Path) -> Path:
    from marimo_studio.authoring import open_workspace

    workspace = open_workspace(notebook_file)
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
    print("Oppretter nytt view...")
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
    print("Et nytt view 'dashboard.html' er opprettet. Oppdater siden for å se viewet.")
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


def validate_github_repository() -> None:
    try:
        repository = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return

    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if status:
        print(
            "Repoet har endringer som ikke er committet. Disse må committes før agenten kan starte.\n"
            "Agenten vil endre notebooken gjennom kommandoer som kan være vanskelige å lese.\n"
            "Derfor må prosjektets nåværende tilstand kunne gjenopprettes.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)


def fetch_github_docs(repo_name: str, docs_path: str) -> Path:
    destination = Path.home() / ".cache" / repo_name
    if destination.is_dir():
        return destination
    print(f"Henter relevant dokumentasjon: {repo_name}...")
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


def choose_notebook(notebooks: list[Path]) -> Path:
    selected = curses.wrapper(_choose_notebook, notebooks)
    return notebooks[selected]


def _choose_notebook(screen: curses.window, notebooks: list[Path]) -> int:
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    selected = 0

    while True:
        screen.clear()
        screen.addstr("Velg Marimo-fil:\n\n")
        for index, notebook in enumerate(notebooks):
            prefix = "❯ " if index == selected else "  "
            style = curses.color_pair(1) if index == selected else 0
            screen.addstr(f"{prefix}{notebook}\n", style)
        screen.addstr("\nBruk ↑/↓ og trykk Enter.")
        key = screen.getch()

        if key == curses.KEY_UP:
            selected = (selected - 1) % len(notebooks)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(notebooks)
        elif key in (curses.KEY_ENTER, 10, 13):
            return selected


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)
