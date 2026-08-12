import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.cost_tracker import calc_cost


def test_known_gemini_model():
    usage = {"input_tokens": 1_000_000, "output_tokens": 500_000}
    cost = calc_cost(usage, "gemini-2.5-flash")
    expected = (1.0 * 0.30) + (0.5 * 2.50)
    assert abs(cost - expected) < 0.001, f"{cost} != {expected}"
    print("OK test_known_gemini_model")


def test_flash_latest():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    cost = calc_cost(usage, "gemini-flash-latest")
    expected = (1.0 * 0.10) + (1.0 * 0.40)
    assert abs(cost - expected) < 0.001
    print("OK test_flash_latest")


def test_unknown_model():
    assert calc_cost({"input_tokens": 1000, "output_tokens": 500}, "unknown-model") == 0.0
    print("OK test_unknown_model")


def test_zero_tokens():
    assert calc_cost({"input_tokens": 0, "output_tokens": 0}, "gemini-2.5-flash") == 0.0
    print("OK test_zero_tokens")


def test_empty_usage():
    assert calc_cost({}, "gemini-2.5-flash") == 0.0
    print("OK test_empty_usage")


def test_claude_rates():
    """Claude rates defined but no calling code yet — verify they parse."""
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000}
    cost = calc_cost(usage, "claude-sonnet-5")
    expected = (1.0 * 3.00) + (0.1 * 15.00)
    assert abs(cost - expected) < 0.001
    print("OK test_claude_rates")


if __name__ == "__main__":
    test_known_gemini_model()
    test_flash_latest()
    test_unknown_model()
    test_zero_tokens()
    test_empty_usage()
    test_claude_rates()
    print("\nAll cost tracker tests passed.")
