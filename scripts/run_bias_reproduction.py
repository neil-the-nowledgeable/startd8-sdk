#!/usr/bin/env python3
"""Reproduction Harness for Cross-Tool Differential Bias Audit (Step S2).

This script drives the benchmark re-authoring process. It is built modularly
to support multiple model vendors, but the current configuration implements
only Google Gemini models via the GenAI SDK. Stubs are provided for OpenAI and
Anthropic.

Keys should be set via environment variables (e.g. GEMINI_API_KEY or GOOGLE_API_KEY)
or run under Doppler:
    doppler run -p startd8 -c dev -- python3 scripts/run_bias_reproduction.py
"""

from __future__ import annotations

import abc
import argparse
import datetime
import hashlib
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / ".startd8" / "bias_audit_reproduction.db"
BRIEF_PATH = REPO / "brief" / "pricing-task-brief.md"

# Safe PYTHONPATH path injection to import startd8 from main repo if not installed
sys.path.insert(0, str(REPO / "src"))
from startd8.prompt_builder import TemplateLoader, PromptGenerator, TemplateContext

# ----------------------------------------------------------------------
# 1. Base Runner Interface
# ----------------------------------------------------------------------

class ModelRunner(abc.ABC):
    """Abstract base class for LLM authoring runs."""

    def __init__(self, model_name: str, temperature: float = 0.7, max_tokens: int = 32768):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abc.abstractmethod
    def run_authoring(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Execute the LLM generation and return the raw output text."""
        pass


# ----------------------------------------------------------------------
# 2. Gemini Specific Runner Implementation
# ----------------------------------------------------------------------

class GeminiRunner(ModelRunner):
    """Google Gemini specific implementation using google-genai."""

    def __init__(self, model_name: str, temperature: float = 0.7, max_tokens: int = 32768):
        super().__init__(model_name, temperature, max_tokens)
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise ImportError(
                    "google-genai package is not installed. "
                    "Install it via `pip install google-genai` or `pipx inject startd8 google-genai`."
                ) from exc
            
            # Check for API key in standard variables
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError(
                    "Google GenAI API Key is missing. "
                    "Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable."
                )
            
            self._client = genai.Client(api_key=api_key)
        return self._client

    def run_authoring(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        client = self._get_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
        )
        if system_prompt:
            config.system_instruction = system_prompt

        try:
            print(f"Calling Gemini model '{self.model_name}'...")
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            raise RuntimeError(f"Gemini API invocation failed: {e}") from e


# ----------------------------------------------------------------------
# 3. OpenAI and Anthropic Stubs (Not Configured in Current Phase)
# ----------------------------------------------------------------------

class OpenAIRunner(ModelRunner):
    """OpenAI Codex / GPT implementation placeholder."""

    def run_authoring(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        raise NotImplementedError(
            "OpenAI runner is not enabled in the current configuration. "
            "Only Google Gemini models are supported by the current configuration."
        )


class AnthropicRunner(ModelRunner):
    """Anthropic Claude Code / Claude implementation placeholder."""

    def run_authoring(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        raise NotImplementedError(
            "Anthropic runner is not enabled in the current configuration. "
            "Only Google Gemini models are supported by the current configuration."
        )


# ----------------------------------------------------------------------
# 4. Database Storage & Manifest Management
# ----------------------------------------------------------------------

def init_db(db_path: Path):
    """Initialize the SQLite schema for tracking runs and artifacts."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Track the metadata for each LLM invocation
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        vendor TEXT NOT NULL,
        model TEXT NOT NULL,
        experiment_type TEXT NOT NULL,
        prompt_hash TEXT NOT NULL,
        prompt TEXT NOT NULL,
        system_prompt TEXT,
        temperature REAL NOT NULL,
        max_tokens INTEGER NOT NULL,
        raw_output TEXT,
        timestamp TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """)

    # Track extracted files / artifacts generated from each run
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(run_id)
    )
    """)
    conn.commit()
    conn.close()


def save_run(db_path: Path, run_id: str, vendor: str, model: str, exp_type: str, 
             prompt: str, sys_prompt: Optional[str], temp: float, max_tok: int, 
             raw_out: str, status: str):
    """Persist a generation run in the DB."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    timestamp = datetime.datetime.utcnow().isoformat()
    
    cursor.execute("""
    INSERT INTO runs (run_id, vendor, model, experiment_type, prompt_hash, prompt, 
                      system_prompt, temperature, max_tokens, raw_output, timestamp, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, vendor, model, exp_type, prompt_hash, prompt, sys_prompt, temp, max_tok, raw_out, timestamp, status))
    
    conn.commit()
    conn.close()


def save_artifact(db_path: Path, artifact_id: str, run_id: str, file_path: str, content: str, status: str):
    """Persist an extracted artifact file in the DB."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    cursor.execute("""
    INSERT INTO artifacts (artifact_id, run_id, file_path, content_hash, content, status)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (artifact_id, run_id, file_path, content_hash, content, status))
    
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# 5. Prompt Templates for Experiments
# ----------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a Senior Principal Software Architect and Systems Engineer specializing in "
    "high-performance, exact-decimal financial and commerce systems. Your code is robust, "
    "idiomatic, completely documented, and strictly follows the provided requirements."
)

TEMPLATE_SUITE = """\
[Task Description]
Using the neutral task brief below, write a comprehensive Node.js test suite for a stateless price calculator.
The test suite will execute assertions against a gRPC server implementing the calculator. 
The test suite must be compatible with the standard Node.js test runner (using `node:test` and `node:assert`).
You must only output the Javascript code for the test suite, enclosed in a ```javascript code block.
Ensure you assert the correct rounding limits, stacking discount strategies, tax precedence logic, and invalid quantity rejections.

CRITICAL STRUCTURAL CONSTRAINTS:
1. The gRPC server implements package `startd8.bench.pricing.v1`, service `PricingService`, with the RPC method `ComputeBasket`.
2. The request/response messages must use the exact field names and structures defined in the task brief (e.g. repeated `LineItem items = 1` inside `ComputeBasketRequest`, and `repeated PricedLineItem items = 1` inside `ComputeBasketResponse`).
3. Ensure your test client loads `pricing.proto` from its directory and queries package `startd8.bench.pricing.v1.PricingService` on method `ComputeBasket`.
4. Your test client must connect to the address specified in the environment variable `SERVER_ADDRESS` (or `process.env.SERVER_ADDRESS`), falling back to `localhost:50051` only if undefined.

[Upstream Neutral Brief]
{brief}
"""

TEMPLATE_SPEC = """\
[Task Description]
Using the neutral task brief below, author the complete, formal gRPC service interface (.proto file) AND the detailed Markdown functional specification describing the stateless calculator.
Your output must be divided clearly:
1. The gRPC contract enclosed in a ```proto code block.
2. The detailed functional requirement documentation in Markdown.

CRITICAL STRUCTURAL CONSTRAINTS:
1. The gRPC server implementation must be entirely self-contained within a single file: `src/pricingservice/server.js`.
2. Do not split your logic across separate files (e.g., calculator.js, constants.js) or write external scripts, as the sandbox environment will only persist `server.js`.
3. The server must load the gRPC definition from `pricing.proto` (which is copied dynamically next to the server file on startup).
4. Do not reference custom filenames like `pricing_calculator.proto` for the protobuf contract. Use the name `pricing.proto`.
5. You MUST explicitly state in the Markdown functional requirements that the server must load the protobuf definition from its local directory (i.e. next to `server.js` using `./pricing.proto` or `path.join(__dirname, 'pricing.proto')`), and that it must not attempt to load it from relative paths like `../../pb/pricing.proto`.

[Upstream Neutral Brief]
{brief}
"""


# ----------------------------------------------------------------------
# 6. Main Controller
# ----------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Differential Bias Audit Reproduction Harness (Step S2)")
    ap.add_argument("--model", default="gemini-2.5-pro", help="Gemini model identifier (default: gemini-2.5-pro)")
    ap.add_argument("--experiment", choices=["suite", "spec"], default="suite", help="Audit experiment type")
    ap.add_argument("--reps", type=int, default=3, help="Number of repetitions/samples (N)")
    ap.add_argument("--temp", type=float, default=0.7, help="Sampling temperature")
    ap.add_argument("--max-tokens", type=int, default=16384, help="Max output token count limit")
    ap.add_argument("--run", action="store_true", help="Execute real LLM calls (default is dry-run)")
    ap.add_argument("--brief-path", type=Path, default=BRIEF_PATH, help="Path to neutral task brief")
    ap.add_argument("--db-path", type=Path, default=DB_PATH, help="Path to reproduction SQLite database")
    args = ap.parse_args(argv)

    if not args.brief_path.exists():
        print(f"Error: Neutral brief file '{args.brief_path}' not found. Run Step S1 first.", file=sys.stderr)
        return 1

    # Initialize the database
    init_db(args.db_path)
    
    # Read the neutral brief
    brief_content = args.brief_path.read_text(encoding="utf-8")
    
    # Render prompt using SDK PromptBuilder (Configurable audit redesign integration)
    loader = TemplateLoader()
    generator = PromptGenerator()
    
    if args.experiment == "suite":
        template = loader.get_template("bias_audit_suite")
        policy_file = REPO / ".startd8" / "bias_audit" / "policy_suite.json"
    else:
        template = loader.get_template("bias_audit_spec")
        policy_file = REPO / ".startd8" / "bias_audit" / "policy_spec.json"

    if not template:
        print(f"Error: Prompt template for '{args.experiment}' not found.", file=sys.stderr)
        return 1

    # Load policy override (if configured)
    policy_str = ""
    if policy_file.exists():
        try:
            import json
            policy_data = json.loads(policy_file.read_text(encoding="utf-8"))
            if isinstance(policy_data, list):
                policy_str = "\n".join(f"- {rule}" for rule in policy_data)
            else:
                policy_str = str(policy_data)
        except Exception as e:
            print(f"Warning: Failed to load policy file {policy_file}: {e}", file=sys.stderr)

    # Build context suggestions (incorporating the configurable POLICY_CONSTRAINTS)
    suggestions = {
        "BRIEF": brief_content,
        "POLICY_CONSTRAINTS": policy_str
    }
    
    context = TemplateContext(
        project_path=REPO,
        variable_values=suggestions,
        auto_filled=suggestions
    )
    result = generator.fill_template(template, context)
    prompt = result.content

    print("=" * 80)
    print(f"Audit Experiment: {args.experiment.upper()}")
    print(f"Target Model:     {args.model}")
    print(f"Repetitions (N):  {args.reps}")
    print(f"Temperature:      {args.temp}")
    print(f"SQLite DB:        {args.db_path}")
    print("=" * 80)

    # Validate configuration and vendor eligibility
    vendor = "google"
    if "gemini" in args.model:
        runner = GeminiRunner(args.model, args.temp, args.max_tokens)
    elif "gpt" in args.model:
        print("Error: OpenAI models are disabled by current configuration.", file=sys.stderr)
        return 1
    elif "claude" in args.model:
        print("Error: Anthropic models are disabled by current configuration.", file=sys.stderr)
        return 1
    else:
        print(f"Error: Unknown model prefix '{args.model}'. Current configuration supports Google Gemini models only.", file=sys.stderr)
        return 1

    if not args.run:
        print("\n[DRY-RUN] Rendered prompt preview:")
        print("-" * 60)
        lines = prompt.splitlines()
        print("\n".join(lines[:10]))
        print("...")
        print("\n".join(lines[-5:]))
        print("-" * 60)
        print("\nDry-run complete. Run with --run and set API keys to call the API.")
        return 0

    print(f"\nStarting {args.reps} repetitions...")
    
    for i in range(1, args.reps + 1):
        run_id = f"run-{args.experiment}-{args.model.replace(':', '_')}-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{i}"
        print(f"\n[Repetition {i}/{args.reps}] Run ID: {run_id}")
        
        try:
            # Execute generation
            raw_output = runner.run_authoring(prompt, SYSTEM_PROMPT)
            print(f"SUCCESS: Generated {len(raw_output)} characters of raw output.")
            
            # Save run metadata
            save_run(
                db_path=args.db_path,
                run_id=run_id,
                vendor=vendor,
                model=args.model,
                exp_type=args.experiment,
                prompt=prompt,
                sys_prompt=SYSTEM_PROMPT,
                temp=args.temp,
                max_tok=args.max_tokens,
                raw_out=raw_output,
                status="success"
            )
            
            # Sub-step to save artifacts (extraction/filtering happens in Step S2b)
            # For S2, we save the full raw output as a provisional artifact
            provisional_path = f"raw_output_{run_id}.txt"
            save_artifact(
                db_path=args.db_path,
                artifact_id=f"art-{run_id}-raw",
                run_id=run_id,
                file_path=provisional_path,
                content=raw_output,
                status="provisional"
            )
            print(f"Saved provisional artifact: {provisional_path}")
            
        except Exception as exc:
            print(f"FAILED Repetition {i}: {exc}", file=sys.stderr)
            save_run(
                db_path=args.db_path,
                run_id=run_id,
                vendor=vendor,
                model=args.model,
                exp_type=args.experiment,
                prompt=prompt,
                sys_prompt=SYSTEM_PROMPT,
                temp=args.temp,
                max_tok=args.max_tokens,
                raw_out=str(exc),
                status="failed"
            )

    print("\nAll repetitions completed. Outputs persisted in database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
