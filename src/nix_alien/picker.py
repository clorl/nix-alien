# ruff: noqa: PLC0415
"""
Unified interface to prompt the user to select an entry in a lit.
Provides presets for pyfzf (default), fzf (via shell), zenity, and may be extended to
add more providers
Attributes:
    DEFAULT_PICKER (str) Default tool
    PICKERS (dict) Config for each picker preset
    RUN_STRATEGIES (dict) Mapping between strategy names and functions, used by PICKERS
"""

from string import Template
from sys import stderr
from textwrap import indent

from .helpers import get_print

_INDENT = "  "

DEFAULT_PICKER: str = "default"

# Shell strategy gets the $title string format argument
PICKERS: dict[str, dict] = {
    "default": {
        "strategy": "pyfzf",
        "args": [
            "--cycle",
            "--prompt",
        ],
    },
    "fzf": {
        "strategy": "shell",
        "command": "fzf",
        "args": ["--cycle", "--prompt", "$title"],
        "success_exit_codes": [0],
        "ignore_exit_codes": [130],
        "entry_separator": " ",
    },
    "zenity": {
        "strategy": "shell",
        "command": "zenity",
        "args": [
            "--list",
            "--title=nix-alien: Choose a package",
            "--text=$title",
            "--column=Libraries",
        ],
        "success_exit_codes": [0],
        "ignore_exit_codes": [1],
        "entry_separator": " ",
    },
}

_pyfzf_prompt = None


def _run_pyfzf(
    entries: list[str], title: str, args: list[str] | None, **kwargs
) -> str | None:
    if args is None:
        args = []
    from shlex import join

    from pyfzf.pyfzf import FzfPrompt

    global _pyfzf_prompt  # noqa: PLW0603

    if _pyfzf_prompt is None:
        _pyfzf_prompt = FzfPrompt()

    options = join([*args, f"{title}> "])
    if result := _pyfzf_prompt.prompt(entries, options):
        return result[0]
    return None


def _run_shell(
    entries: list[str],
    title: str,
    command: str,
    args: list[str] | None,
    success_exit_codes: list[int] | None,
    ignore_exit_codes: list[int] | None,
    entry_separator: str = "\n",
    **kwargs,
) -> str | None:
    if args is None:
        args = []
    if success_exit_codes is None:
        success_exit_codes = []
    if ignore_exit_codes is None:
        ignore_exit_codes = []

    command = command.strip()

    if not command:
        raise ValueError(
            "Given 'command' parameter is empty or whitespace only: '{command}'"
        )
    formatted_args = [Template(arg).safe_substitute(title=title) for arg in args]

    full_cmd = [command, *formatted_args]
    try:
        import subprocess

        proc = subprocess.run(
            full_cmd,
            input=entry_separator.join(entries),
            text=True,
            capture_output=True,
            check=False,
        )

        if proc.returncode in success_exit_codes:
            return proc.stdout.strip() or None
        if proc.returncode in ignore_exit_codes:
            return None
        err = proc.stderr.strip() or "No error message returned."
        raise RuntimeError(f"Exit code {proc.returncode}: \n{err}")
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Could not find the binary '{command}' in your PATH."
        ) from e
    except Exception as e:
        pargs = " ".join(formatted_args)
        raise RuntimeError(
            f"Failed to execute shell command: "
            f"{command} {pargs}'\n{indent(str(e), _INDENT)}"
        ) from e


RUN_STRATEGIES = {"pyfzf": _run_pyfzf, "shell": _run_shell}


def prompt(
    entries: list[str],
    picker_id: str = DEFAULT_PICKER,
    prompt_title: str = "Select candidate",
    silent: bool = False,
) -> str | None:
    """
    Executes a picker to request user input, eg. fzf
    Args:
        entries: List of strings to present to the user.
        picker_id: What picker to use. The list of valid picker configs is found in the
        PICKERS dictionary
        prompt_title: Title to display on the prompt
    Returns:
        str | None: The selected provider name. Raises an exc
    """
    _print = get_print(silent)
    picker_id = picker_id.strip()
    picker_config: dict | None = PICKERS.get(picker_id)
    if picker_config is None:
        _print(
            f"Argument '{picker_id}' is not the name of an existing picker preset."
            f"Valid names are: '{', '.join(PICKERS.keys())}'",
            file=stderr,
        )
        return None

    strat_name = picker_config.get("strategy", "").strip()
    if not strat_name:
        _print(
            f"Internal Error: Preset picker config {picker_id} "
            "has an empty or null 'strategy' field.",
            file=stderr,
        )
        return None

    executor = RUN_STRATEGIES.get(strat_name)
    if not executor:
        _print(
            f"Internal Error: Preset picker config {picker_id}"
            f"uses an unknown strategy called '{strat_name}'",
            file=stderr,
        )
        return None
    if not callable(executor):
        _print(
            f"Internal Error: Strategy '{strat_name}' points to a value that is"
            "not a function.",
            file=stderr,
        )
        return None

    result = None
    try:
        result = executor(entries, prompt_title, **picker_config)
    except Exception as e:
        _print(
            "\n".join(
                [
                    f"Picker preset '{picker_id}' (with strategy '{strat_name}') "
                    f"(called with params: title={prompt_title}, "
                    f"config={picker_config!s}) raised the following error:",
                    indent(str(e), _INDENT),
                ]
            ),
            file=stderr,
        )
    return result
