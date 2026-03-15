"""
Cost Estimator
---------------
Estimates the cost of a full StaySweep search.

Using Google Gemini 2.0 Flash free tier:
  - 15 requests per minute
  - 1,000,000 tokens per day
  - Cost: $0.00

This module is kept for informational purposes (token usage tracking)
and to maintain compatibility with the CLI.
"""


def estimate_cost(
    n_hotels: int,
    avg_reviews_per_hotel: int = 15,
    avg_images_per_hotel: int = 6,
    tokens_per_image: int = 800,
) -> dict:
    """Returns a cost breakdown dict. All costs are $0 on the free tier."""

    # Query parsing (once)
    qp_input = 300
    qp_output = 150

    # Text analysis (per hotel)
    ta_input = (avg_reviews_per_hotel * 80 + 500) * n_hotels
    ta_output = 300 * n_hotels

    # Vision analysis (per hotel, ~70% pass the gate)
    hotels_with_vision = int(n_hotels * 0.7)
    va_input = (avg_images_per_hotel * tokens_per_image + 600) * hotels_with_vision
    va_output = 400 * hotels_with_vision

    # Scoring + summary (per hotel)
    sc_input = 600 * n_hotels
    sc_output = 200 * n_hotels

    total_input = qp_input + ta_input + va_input + sc_input
    total_output = qp_output + ta_output + va_output + sc_output

    return {
        "n_hotels": n_hotels,
        "hotels_with_vision": hotels_with_vision,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "cost_input_usd": 0.0,
        "cost_output_usd": 0.0,
        "total_cost_usd": 0.0,
        "breakdown": {
            "query_parsing": 0.0,
            "text_analysis": 0.0,
            "vision_analysis": 0.0,
            "scoring": 0.0,
        }
    }


def print_cost_estimate(n_hotels: int):
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    est = estimate_cost(n_hotels)

    table = Table(title=f"Estimated Usage ({n_hotels} hotels)",
                  box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Stage")
    table.add_column("Est. Tokens", justify="right")
    table.add_column("Cost", justify="right")

    stages = {
        "Query Parsing": est["total_input_tokens"] // 20,  # rough split
        "Text Analysis": est["total_input_tokens"] // 3,
        "Vision Analysis": est["total_input_tokens"] // 2,
        "Scoring": est["total_input_tokens"] // 8,
    }

    for stage, tokens in stages.items():
        table.add_row(stage, f"~{tokens:,}", "[green]$0.00[/]")

    table.add_section()
    table.add_row("[bold]Total[/]",
                  f"[bold]~{est['total_input_tokens'] + est['total_output_tokens']:,}[/]",
                  "[bold green]$0.00 (free tier)[/]")

    console.print(table)
    console.print(f"  [dim]Using Gemini 2.0 Flash free tier (15 RPM, 1M tokens/day)[/]")
    console.print(f"  [dim]({est['hotels_with_vision']} of {n_hotels} hotels will get vision analysis)[/]")
