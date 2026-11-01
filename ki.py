# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "marimo-studio==0.4.0",
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
from typing import NoReturn, cast

from dataclasses import dataclass
from pathlib import Path

IS_DAPLA_ENVIRONMENT = "DAPLA_ENVIRONMENT" in os.environ
MARIMO_ADRESS = f"http://localhost:{8080 if IS_DAPLA_ENVIRONMENT else 2718}"

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
class Source:
    path: Path
    usage: str


@dataclass
class AgentSession:
    sources: list[Source]
    system_prompt: str
    initial_prompt: str
    writeable_directory: Path


def main() -> None:
    arguments = parse_args()
    validate_github_repository()
    notebooks = find_active_notebooks()
    if not notebooks:
        exit_because_no_valid_marimo_session()
    notebook_file = notebooks[0] if len(notebooks) == 1 else choose_notebook(notebooks)
    view = get_view(notebook_file)
    html_file = view.joinpath("index.html")

    sources = get_sources(notebook_file)
    system_prompt = get_system_prompt(sources, notebook_file, html_file)
    print(
        f"\nAktive Marimo-filer\n"
        f"  Notebook: {notebook_file}\n"
        f"  View:     {html_file}\n"
        f"\n"
        f"Relvant kontekst er lastet.\n"
        f"\n"
        f"{ITALIC_TEXT_START}Agenten vil få automatisk skrivetilgang til {notebook_file.parent} (uten bekreftelsesmelding). "
        f"Agenten vil ikke kunne skrive til filer utenfor dette og ikke til bøtter. "
        f"Agenten har ikke tilgang til eksterne internettsider, men leser lokal dokumentasjon. "
        f"Det anbefales derfor å installere relevante Python-pakker i notebooken på forhånd, "
        f"slik at agenten får rask tilgang til relevant pakkedokumentasjon.\n"
        f"\n"
        f"Når agenten er ferdig kan du se alle endringene med kommandoen "
        f"{GREEN_TEXT_START}git diff{GREEN_TEXT_STOP}.\n"
        f"Kommandoen {GREEN_TEXT_START}git restore .{GREEN_TEXT_STOP}{ITALIC_TEXT_STOP} "
        f"kan brukes til å angre agentens endringer.\n"
        f"\n"
        f"{GREEN_TEXT_START}Skriv inn hva du ønsker skal gjøres og trykk deretter Enter for å starte agenten (eller Ctrl+C for å avbryte).{GREEN_TEXT_STOP}\n"
    )

    initial_prompt = input(f"{GREEN_TEXT_START}> {GREEN_TEXT_STOP}")
    agent_session = AgentSession(
        sources, system_prompt, initial_prompt, notebook_file.parent
    )
    if arguments.dry_run:
        print(build_prompt(agent_session))
    else:
        start_agent(agent_session)


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
        ["git", "status", "--porcelain"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    if status:
        print(
            "Repoet har endringer som ikke er commited. Disse må comittes før agenten kan starte.\n"
            "Agenten kommer til å få automatisk skrivetilgang og prosjektets nåværende tilstand må derfor kunne gjenopprettes.",
            file=sys.stderr,
        )
        raise SystemExit(1)


def build_prompt(agent_session: AgentSession) -> str:
    prompt = "# System prompt\n\n"
    prompt += agent_session.system_prompt
    prompt += f"\n\n# User prompt (respond in same language)\n\n{agent_session.initial_prompt}"
    return prompt


def start_agent(agent_session: AgentSession) -> None:
    command = ["opencode", "--prompt", build_prompt(agent_session)]
    subprocess.run(command, cwd=agent_session.writeable_directory, check=True)


def get_sources(notebook_file: Path) -> list[Source]:
    notebook_python_packages: Source = Source(
        Path(get_notebook_site_packages(notebook_file)),
        ("Always read relevant API documentation here before using packages."),
    )

    dapla_manual: Source = Source(
        fetch_github_docs(
            "statisticsnorway/dapla-manual", "dapla-manual/statistikkere"
        ),
        (
            "Always read relevant documentation from here before developing the notebook and using packages. "
            "It provides SSB-specific guidelines that should be followed."
        ),
    )

    designsystemet: Source = Source(
        fetch_github_docs("digdir/designsystemet", "apps/www/app/content"),
        (
            "Read relevant documentation from here before developing the html view. "
            "Always prefer using designsystemet components and design tokens instead of hardcoded css values. "
            "In particular, SSB theming come out of the box with the existing css imports."
        ),
    )


    marimo_pair: Source = Source(
        Path.home() / ".agents" / "skills" / "marimo-pair",
        (
            "Use this skill to develop the notebook, instead of making direct edits to the file."
            f"It is not necessary to discover Marimo servers; the Marimo server is available at {MARIMO_ADRESS}."
            "You must give the user a short explanation before each time you use the marimo-pair script."
        ),
    )

    marimo_notebook: Source = Source(
        Path.home() / ".agents" / "skills" / "marimo-notebook",
        (    "Use this skill instead of marimo-pair when you only need to make minor changes,"
            "that can be made through direct edits to the notebook."
            "When using marimo-pair, use this skill to understand how Marimo outputs work. "
            "Summary: always put the output in a variable and use that as the last expression of the cell."
        ),
    )

    #TODO fetch github docs from marimo-team/marimo-studio, path "docs"
    #say that it can be used to understand how marimo-studio works, but it's generally not necessary

    return [
        notebook_python_packages,
        dapla_manual,
        designsystemet,
        marimo_pair,
        marimo_notebook,
    ]


def get_system_prompt(
    sources: list[Source], notebook_file: Path, html_file: Path
) -> str:
    resources = "\n".join(f"  - {source.path}: {source.usage}" for source in sources)
    return (
        f"Your job is to help develop the reactive Marimo application `{notebook_file}` "
        f"and its Marimo Studio HTML view `{html_file}`. You should not edit other files.\n"
        "Try to keep logic in the notebook and layout/styling in the HTML view.\n"
        "Always use marimo-pair when developing the notebook, and inspect for errors.\n"
        "You must *not* test by changing the user's real data.\n"
        "Use English for code and Norwegian for output.\n"
        "Avoid implementing large amounts of logic and data processing; prefer a thin layer over existing SSB packages.\n"
        "The following is the list of available resources and when/how they should be used.\n"
        f"{resources}\n"
        "Do not use the shell tool to read them; only use the grep, glob and read tools.\n"
        "Based on your findings, use the question tools to clarify the user's requirements, "
        "e.g. which UI components they want to use or how they want to use the Python packages.\n"
    )


def exit_because_no_valid_marimo_session() -> NoReturn:
    print(
        "Du må ha en Marimo-fil som er lagret i dashboards-mappa og er åpnet i Marimo-grensesnittet. "
        "Grunnen til at den må være i dashboards-mappa er at agenten får automatisk skrivetilgang til denne mappa, men ikke til andre mapper.",
        file=sys.stderr,
    )
    raise SystemExit(1)


def find_active_notebooks() -> list[Path]:
    try:
        with urllib.request.urlopen(
            f"{MARIMO_ADRESS}/api/sessions", timeout=2
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


def run_in_marimo_session(notebook_file: Path, code: str) -> str:
    command = [
        "bash",
        os.path.expanduser("~/.agents/skills/marimo-pair/scripts/execute-code.sh"),
        "--url",
        MARIMO_ADRESS,
        "--file",
        str(notebook_file),
        "-c",
        code,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        exit_because_no_valid_marimo_session()
    return result.stdout


def get_notebook_site_packages(notebook_file: Path) -> str:
    return run_in_marimo_session(
        notebook_file,
        "import sysconfig; print(sysconfig.get_path('purelib'))",
    ).strip()


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
