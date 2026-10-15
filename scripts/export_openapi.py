import json
from pathlib import Path

from vetorthoplan.bootstrap import create_app


def main() -> None:
    output = Path("openapi/openapi.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(create_app().openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)


if __name__ == "__main__":
    main()

