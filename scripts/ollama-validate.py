#!/usr/bin/env python3
"""Validate Ollama + startd8 configuration."""

import sys
import json
import urllib.request
import urllib.error

OLLAMA_BASE = "http://localhost:11434"


def check_ollama_server():
    """Check Ollama is reachable."""
    try:
        resp = urllib.request.urlopen(f"{OLLAMA_BASE}/api/tags", timeout=5)
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        print(f"  Server: {OLLAMA_BASE}")
        print(f"  Models: {', '.join(models) or '(none)'}")
        return models
    except urllib.error.URLError as e:
        print(f"  FAIL: Cannot reach Ollama at {OLLAMA_BASE} — {e}")
        return []


def check_startd8_provider():
    """Check startd8 Ollama provider loads."""
    try:
        from startd8.providers.registry import ProviderRegistry
        registry = ProviderRegistry()
        provider = registry.get_provider("ollama")
        if provider:
            print(f"  Provider: {provider.display_name}")
            print(f"  Catalog models: {', '.join(provider.supported_models[:5])}...")
            return provider
        else:
            print("  FAIL: 'ollama' provider not registered")
            return None
    except Exception as e:
        print(f"  FAIL: {e}")
        return None


def check_agent_creation(provider, model):
    """Check agent can be created for a specific model."""
    try:
        agent = provider.create_agent(model)
        print(f"  Agent: {agent.name} (model={model})")
        print(f"  Base URL: {agent.base_url}")
        return agent
    except Exception as e:
        print(f"  FAIL: Cannot create agent for {model} — {e}")
        return None


def main():
    ok = True

    print("\n[1/3] Ollama server")
    models = check_ollama_server()
    if not models:
        print("\n  Hint: run 'ollama serve' in another terminal\n")
        sys.exit(1)

    print("\n[2/3] startd8 provider")
    provider = check_startd8_provider()
    if not provider:
        ok = False

    print("\n[3/3] Agent creation")
    for model in models:
        agent = check_agent_creation(provider, model) if provider else None
        if not agent:
            ok = False

    print()
    if ok:
        print("All checks passed. Run ollama-sample-requests.py to test generation.")
    else:
        print("Some checks failed. Fix the issues above before running sample requests.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
