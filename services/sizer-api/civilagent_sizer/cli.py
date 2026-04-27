"""Command-line entry point for civilagent-sizer."""

import json
from pathlib import Path

import click

from civilagent_sizer.layout import size_plan_layout
from civilagent_sizer.schemas import PlanInput


@click.group()
def main() -> None:
    """Run deterministic structural member sizing commands."""


@main.command()
@click.argument("plan_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--layout", "layout_name", required=True, help="Layout name to size, e.g. A or B.")
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Optional JSON output path.",
)
def size(plan_json: Path, layout_name: str, output_path: Path | None) -> None:
    """Size one layout from a structured sample-plan JSON file."""

    plan = PlanInput.model_validate_json(plan_json.read_text(encoding="utf-8"))
    result = size_plan_layout(plan, layout_name)
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, indent=2)
    if output_path is not None:
        output_path.write_text(rendered + "\n", encoding="utf-8")
    click.echo(rendered)


if __name__ == "__main__":
    main()
