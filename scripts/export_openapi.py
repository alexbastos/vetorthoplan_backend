import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from vetorthoplan.bootstrap import create_app


def main() -> None:
    schema = create_app().openapi()
    schema["info"].update(
        {
            "x-git-branch": git_value(("branch", "--show-current"), fallback="unknown"),
            "x-git-commit": git_value(("rev-parse", "HEAD"), fallback="unknown"),
            "x-generated-at": datetime.now(UTC).isoformat(),
        }
    )
    content = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    outputs = (Path("openapi/openapi.json"), Path("docs/openapi.json"))
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(output)


def git_value(args: tuple[str, ...], fallback: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip() or fallback
    except (OSError, subprocess.CalledProcessError):
        return fallback


if __name__ == "__main__":
    main()
