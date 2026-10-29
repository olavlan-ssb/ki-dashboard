# /// script
# requires-python = ">=3.12"
# ///

import argparse
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
    return f'''\
# Context

I want help developing a reactive Marimo application in {app_file}.

## The Marimo Python API for editing a Marimo notebook

Result of `import marimo._code_mode as cm; help(cm)`:

{get_marimo_python_api_docs(app_file)}

## The current content of Marimo notebook

{get_notebook_content(app_file)}

## Instructions and prompt

Use the marimo-pair skill to develop the notebook.
You do not have to run the setup commands again.

Use the marimo-notebook skill to understand Marimo best practices.
Note especially that outputs must be assigned to variables and used as the final expression of the cell.

The notebook changes **must** be made through this shell command (see usage in marimo-pair skill):

bash ~/.agents/skills/marimo-pair/scripts/execute-code.sh --url "http://localhost:{MARIMO_SERVER_PORT}" --file "{app_file}"

Before every change, you **must** first explain the change to me.
Prefer running the command as few times as possible to avoid overwhelming me with requests.
Avoid extensive testing - I will test the app myself and provide feedback.
Do **not** run other shell commands.

Before using packages, always read the relevant package APIs directly from the source: {get_notebook_environment(app_file)}.
Do not use the **shell** tool for this; use the glob, grep and read tools in the folder.

Use English for code and Norwegian for output.
Do not write large amounts of logic or data processing - prefer a thin interactive layer over existing SSB packages.
The notebook should only have the plain interactive components.
It should **not** have html and css.
It should **not** have a headline.
Prefer **not** combining into stacks - rather have one small output for each cell. 
Inform user that all app design (layout and styling) should be done through the `ki-layout` terminal command.

Start by reading the relevant package documentation directly from the source, including the Marimo UI component APIs. 
Then use the question tool to clarify the requirements -  give me concrete alternatives based on the main prompt and available package API.

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
        parser.error("det andre argumentet må være en kort beskrivelse av ønsket endring i filen")
    return Arguments(
        dry_run=args.dry_run,
        app_file=args.app_file,
        prompt=args.prompt,
    )


def exit_because_notebook_session_is_not_active(app_file: Path) -> None:
    print(f"Filen '{app_file}' må være åpnet i Marimo-grensesnittet", file=sys.stderr)
    raise SystemExit(1)


def execute_python_in_notebook_session(app_file: Path, code: str) -> str:
    command = [
        "bash",
        os.path.expanduser("~/.agents/skills/marimo-pair/scripts/execute-code.sh"),
        "--url",
        f"http://localhost:{MARIMO_SERVER_PORT}",
        "--file",
        str(app_file),
        "-c",
        code,
    ]
    result = subprocess.run(command, capture_output=True, text=True )
    if result.returncode != 0:
        exit_because_notebook_session_is_not_active(app_file)
    return result.stdout


def get_notebook_environment(app_file: Path) -> str:
    result = subprocess.run(
        ["uv", "python", "find", "--script", str(app_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        exit_because_notebook_session_is_not_active(app_file)
    return result.stdout.strip()


def get_marimo_python_api_docs(app_file: Path) -> str:
    return execute_python_in_notebook_session(app_file, "import marimo._code_mode as cm; help(cm)")


def get_notebook_content(app_file: Path) -> str:
    return execute_python_in_notebook_session(
        app_file,
        textwrap.dedent(
            """\
            import marimo._code_mode as cm

            async with cm.get_context() as ctx:
                for cell_id, cell in ctx.cells.items():
                    print(f"### Cell {cell_id}")
                    print("```python")
                    print(cell.code)
                    print("```")
            """
        ),
    )


if __name__ == "__main__":
    main()
