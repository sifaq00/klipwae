GEMINI_RATES = {
    # gemini-flash-latest = alias ke model flash terbaru; rate bisa berubah.
    # Pakai rate 2.0-flash sebagai estimasi konservatif. Upgrade ke lookup
    # dinamis kalau cost tracking perlu akurasi penuh (Fase 6).
    "gemini-flash-latest": {"input": 0.10, "output": 0.40},
    "gemini-flash-lite-latest": {"input": 0.075, "output": 0.30},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}

CLAUDE_RATES = {
    "claude-sonnet-5": {"input": 3.00, "output": 15.00},
}


def calc_cost(usage: dict, model: str) -> float:
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    rates = GEMINI_RATES.get(model) or CLAUDE_RATES.get(model)
    if not rates:
        return 0.0
    return (input_tokens / 1_000_000 * rates["input"]) + (output_tokens / 1_000_000 * rates["output"])
