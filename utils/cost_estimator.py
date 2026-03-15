"""
Cost Estimator
---------------
Estimates the Claude API cost of a full Hotel Hunter search before running it.

Pricing (as of 2025, claude-sonnet-4):
  Input:  $3.00 per 1M tokens
  Output: $15.00 per 1M tokens

Rough token estimates per operation:
  - Query parsing:      ~300 input + 150 output
  - Text analysis:      ~2,000 input + 300 output  (per hotel)
  - Vision analysis:    ~1,500 input + 400 output + ~800 tokens per image
  - Score + summary:    ~600 input + 200 output    (per hotel)
"""

# Pricing per token (USD)
INPUT_PRICE_PER_TOKEN  = 3.00 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 15.00 / 1_000_000


def estimate_cost(
    n_hotels: int,
    avg_reviews_per_hotel: int = 15,
    avg_images_per_hotel: int = 6,
    tokens_per_image: int = 800,
) -> dict:
    """Returns a cost breakdown dict."""

    # Query parsing (once)
    qp_input  = 300
    qp_output = 150

    # Text analysis (per hotel)
    # ~80 tokens/review + system prompt overhead
    ta_input  = (avg_reviews_per_hotel * 80 + 500) * n_hotels
    ta_output = 300 * n_hotels

    # Vision analysis (per hotel, only hotels that pass text gate)
    # Assume 70% pass the gate
    hotels_with_vision = int(n_hotels * 0.7)
    va_input  = (avg_images_per_hotel * tokens_per_image + 600) * hotels_with_vision
    va_output = 400 * hotels_with_vision

    # Scoring + summary (per hotel)
    sc_input  = 600 * n_hotels
    sc_output = 200 * n_hotels

    total_input  = qp_input  + ta_input  + va_input  + sc_input
    total_output = qp_output + ta_output + va_output + sc_output

    cost_input  = total_input  * INPUT_PRICE_PER_TOKEN
    cost_output = total_output * OUTPUT_PRICE_PER_TOKEN
    total_cost  = cost_input + cost_output

    return {
        "n_hotels": n_hotels,
        "hotels_with_vision": hotels_with_vision,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "cost_input_usd": round(cost_input, 4),
        "cost_output_usd": round(cost_output, 4),
        "total_cost_usd": round(total_cost, 4),
        "breakdown": {
            "query_parsing": round((qp_input * INPUT_PRICE_PER_TOKEN +
                                    qp_output * OUTPUT_PRICE_PER_TOKEN), 5),
            "text_analysis": round((ta_input * INPUT_PRICE_PER_TOKEN +
                                    ta_output * OUTPUT_PRICE_PER_TOKEN), 4),
            "vision_analysis": round((va_input * INPUT_PRICE_PER_TOKEN +
                                      va_output * OUTPUT_PRICE_PER_TOKEN), 4),
            "scoring": round((sc_input * INPUT_PRICE_PER_TOKEN +
                              sc_output * OUTPUT_PRICE_PER_TOKEN), 4),
        }
    }


def print_cost_estimate(n_hotels: int):
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    est = estimate_cost(n_hotels)

    table = Table(title=f"Estimated API Cost ({n_hotels} hotels)",
                  box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Stage")
    table.add_column("Est. Cost", justify="right")

    for stage, cost in est["breakdown"].items():
        table.add_row(stage.replace("_", " ").title(), f"${cost:.4f}")

    table.add_section()
    table.add_row("[bold]Total[/]", f"[bold]${est['total_cost_usd']:.4f}[/]")

    console.print(table)
    console.print(f"  [dim]({est['hotels_with_vision']} of {n_hotels} hotels will get vision analysis)[/]")
