"""
Interactive Hotel Hunter CLI
------------------------------
Run without arguments for an interactive session:
    python cli.py

Or pass args directly:
    python cli.py --query "dark purple couch" --city "New York"
"""

import asyncio
import sys
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich import box

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from main import run
from utils.cost_estimator import print_cost_estimate

console = Console()

EXAMPLE_QUERIES = [
    ("dark purple couch", "New York"),
    ("rooftop pool with mountain views", "Denver"),
    ("fireplace in the room", "Aspen"),
    ("pink neon sign in lobby", "Las Vegas"),
    ("claw foot bathtub in room", "New Orleans"),
    ("library with floor-to-ceiling bookshelves", "Boston"),
]


def show_banner():
    console.print(Panel(
        "[bold cyan]🏨 Hotel Hunter[/]\n"
        "[dim]Find hyper-specific hotel features using AI vision + review analysis[/]",
        box=box.DOUBLE_EDGE,
        padding=(1, 4),
    ))


def show_examples():
    console.print("\n[bold]Example searches:[/]")
    for i, (query, city) in enumerate(EXAMPLE_QUERIES, 1):
        console.print(f"  [dim]{i}.[/] \"{query}\" in {city}")
    console.print()


async def interactive_session():
    show_banner()
    show_examples()

    # Get query
    query = Prompt.ask("[bold]What feature are you looking for?[/]",
                       default="dark purple couch")

    # Get city
    city = Prompt.ask("[bold]Which city?[/]", default="New York")

    # Show cost estimate
    console.print()
    print_cost_estimate(n_hotels=12)  # typical result count
    console.print()

    confirmed = Confirm.ask("Proceed with search?", default=True)
    if not confirmed:
        console.print("[dim]Search cancelled.[/]")
        return

    console.print()
    await run(query, city)


async def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Hotel Hunter — Find specific features in hotels using AI"
    )
    parser.add_argument("--query", "-q", help='Feature to find, e.g. "dark purple couch"')
    parser.add_argument("--city", "-c", help='City to search in, e.g. "New York"')
    parser.add_argument("--estimate", "-e", action="store_true",
                        help="Only show cost estimate, don't run the search")
    args = parser.parse_args()

    if args.estimate:
        print_cost_estimate(n_hotels=12)
        return

    if args.query and args.city:
        await run(args.query, args.city)
    else:
        await interactive_session()


if __name__ == "__main__":
    asyncio.run(main())
