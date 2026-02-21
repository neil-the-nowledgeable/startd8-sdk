#!/usr/bin/env python3
"""Run sample requests through Ollama via startd8 agents."""

import asyncio
import sys
import time
import json
import urllib.request

OLLAMA_BASE = "http://localhost:11434"

SAMPLES = [
    {
        "label": "Simple completion",
        "prompt": "What is OpenTelemetry in one sentence?",
    },
    {
        "label": "Code generation",
        "prompt": "Write a Python function that computes SHA-256 of a file. Only output the code, no explanation.",
    },
    {
        "label": "Structured output",
        "prompt": 'Return a JSON object with keys "name", "purpose", "language" describing the Python requests library. Only output valid JSON.',
    },
]


def discover_models():
    """Get installed Ollama models."""
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5)
        data = json.loads(resp.read())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def run_sample(agent, label, prompt):
    """Run one sample and report results."""
    print(f"\n  [{label}]")
    print(f"  Prompt: {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

    start = time.monotonic()
    try:
        result = agent.generate(prompt)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        text = result.text
        tokens = result.token_usage
        # Truncate long responses for display
        display = text.strip()[:300]
        if len(text.strip()) > 300:
            display += "..."
        token_info = ""
        if tokens:
            token_info = f", {tokens.input}in/{tokens.output}out tokens"
        print(f"  Response ({elapsed_ms}ms, {len(text)} chars{token_info}):")
        for line in display.split("\n"):
            print(f"    {line}")
        return True
    except Exception as e:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        print(f"  FAIL ({elapsed_ms}ms): {e}")
        return False


def test_model(model):
    """Run all samples against one model."""
    from startd8.providers.registry import ProviderRegistry
    registry = ProviderRegistry()
    provider = registry.get_provider("ollama")
    agent = provider.create_agent(model)

    print(f"\n{'='*60}")
    print(f"Model: {model}")
    print(f"{'='*60}")

    passed = 0
    for sample in SAMPLES:
        ok = run_sample(agent, sample["label"], sample["prompt"])
        if ok:
            passed += 1

    print(f"\n  Result: {passed}/{len(SAMPLES)} passed")
    return passed == len(SAMPLES)


def main():
    models = discover_models()
    if not models:
        print("No Ollama models found. Run ollama-validate.py first.")
        sys.exit(1)

    # If a model was specified on the command line, use only that one
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if target not in models:
            print(f"Model '{target}' not found. Available: {', '.join(models)}")
            sys.exit(1)
        models = [target]

    all_passed = True
    for model in models:
        ok = test_model(model)
        if not ok:
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print(f"All {len(models)} model(s) passed all samples.")
    else:
        print("Some samples failed. Check output above.")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
