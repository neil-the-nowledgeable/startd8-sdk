"""
Tests for truncation detection functionality.

This module tests the truncation detection utilities that prevent
corrupted/incomplete LLM outputs from being saved or passed to
subsequent pipeline steps.
"""

import pytest
from startd8.truncation_detection import (
    detect_truncation,
    TruncationResult,
    get_truncation_warning_message,
    estimate_document_sections,
    infer_code_language,
    get_expected_sections_for_code,
)
from startd8.exceptions import TruncationError


class TestDetectTruncation:
    """Tests for the detect_truncation function."""
    
    def test_empty_output_is_truncated(self):
        """Empty output should always be detected as truncated."""
        result = detect_truncation("", "Some input")
        assert result.is_truncated
        assert result.confidence == 1.0
        assert "Empty output" in result.indicators
    
    def test_whitespace_only_is_truncated(self):
        """Whitespace-only output should be detected as truncated."""
        result = detect_truncation("   \n\t  ", "Some input")
        assert result.is_truncated
        assert result.confidence == 1.0
    
    def test_complete_output_not_truncated(self):
        """Normal complete output should not be detected as truncated."""
        result = detect_truncation(
            "This is a complete sentence.\n\nEnd of document.",
            "Test input"
        )
        assert not result.is_truncated
        assert result.confidence == 0.0
        assert len(result.indicators) == 0
    
    def test_unclosed_code_block(self):
        """Unclosed code block should be detected."""
        result = detect_truncation(
            "Here is some code:\n```python\ndef hello():\n    print('hi')",
            "Test input"
        )
        assert result.is_truncated
        assert any("code block" in ind.lower() for ind in result.indicators)
    
    def test_closed_code_block_ok(self):
        """Properly closed code block should not trigger truncation."""
        result = detect_truncation(
            "Here is some code:\n```python\ndef hello():\n    print('hi')\n```\nDone.",
            "Test input"
        )
        # Should not be truncated due to code blocks
        code_block_issues = [ind for ind in result.indicators if "code block" in ind.lower()]
        assert len(code_block_issues) == 0
    
    def test_unclosed_json_braces(self):
        """Unclosed JSON braces should be detected."""
        result = detect_truncation(
            '{"key": "value", "nested": {"inner":',
            "Test input"
        )
        assert result.is_truncated
        assert any("brace" in ind.lower() or "json" in ind.lower() for ind in result.indicators)
    
    def test_unclosed_json_brackets(self):
        """Unclosed JSON brackets should be detected."""
        result = detect_truncation(
            '["item1", "item2", ["nested"',
            "Test input"
        )
        assert result.is_truncated
        assert any("bracket" in ind.lower() or "json" in ind.lower() for ind in result.indicators)
    
    def test_mid_sentence_ending_with_comma(self):
        """Ending with comma should be flagged."""
        result = detect_truncation(
            "This is a list of items: one, two,",
            "Test input"
        )
        assert any("comma" in ind.lower() or "mid-sentence" in ind.lower() for ind in result.indicators)
    
    def test_mid_sentence_ending_with_colon(self):
        """Ending with colon should be flagged."""
        result = detect_truncation(
            "The following items are:",
            "Test input"
        )
        assert any("colon" in ind.lower() or "mid-sentence" in ind.lower() for ind in result.indicators)
    
    def test_output_too_short_ratio(self):
        """Output much shorter than input should be flagged."""
        long_input = "A" * 10000
        short_output = "B" * 1000  # 10% of input
        
        result = detect_truncation(
            short_output,
            long_input,
            min_output_ratio=0.3  # Expect at least 30%
        )
        assert result.is_truncated
        assert any("short" in ind.lower() or "ratio" in ind.lower() for ind in result.indicators)
        assert result.details.get("length_ratio") == pytest.approx(0.1, rel=0.01)
    
    def test_output_length_ratio_acceptable(self):
        """Output with acceptable length ratio should not be flagged for length."""
        input_text = "A" * 1000
        output_text = "B" * 500  # 50% of input
        
        result = detect_truncation(
            output_text,
            input_text,
            min_output_ratio=0.3  # Expect at least 30%
        )
        # Should not have length ratio issue
        length_issues = [ind for ind in result.indicators if "short" in ind.lower() and "ratio" in ind.lower()]
        assert len(length_issues) == 0
    
    def test_strict_mode_more_sensitive(self):
        """Strict mode should have lower threshold for detection."""
        # Text with minor issues that might not trigger in normal mode
        text = "This is almost complete but"
        
        normal_result = detect_truncation(text, "Test", strict_mode=False)
        strict_result = detect_truncation(text, "Test", strict_mode=True)
        
        # Strict mode should have same or higher confidence
        assert strict_result.confidence >= normal_result.confidence
        # If confidence is borderline, strict might flag it while normal doesn't
        if 0.3 <= normal_result.confidence < 0.5:
            assert strict_result.is_truncated and not normal_result.is_truncated
    
    def test_missing_expected_sections(self):
        """Missing expected sections should be flagged."""
        result = detect_truncation(
            "# Introduction\n\nSome intro text.",
            "Test input",
            expected_sections=["Introduction", "Methods", "Results", "Conclusion"]
        )
        # Should flag missing sections
        assert "missing_sections" in result.details
        assert len(result.details["missing_sections"]) >= 3  # At least Methods, Results, Conclusion
    
    def test_all_expected_sections_present(self):
        """All expected sections present should not flag."""
        result = detect_truncation(
            "## Introduction\nText\n## Methods\nText\n## Results\nText\n## Conclusion\nText",
            "Test input",
            expected_sections=["Introduction", "Methods", "Results", "Conclusion"]
        )
        # Should not have section issues
        if "missing_sections" in result.details:
            assert len(result.details["missing_sections"]) < 2  # Allow 1 minor mismatch


class TestTruncationResult:
    """Tests for TruncationResult dataclass."""
    
    def test_bool_true_when_truncated(self):
        """TruncationResult should be truthy when truncated."""
        result = TruncationResult(
            is_truncated=True,
            confidence=0.8,
            indicators=["Test"],
            details={}
        )
        assert bool(result) is True
    
    def test_bool_false_when_not_truncated(self):
        """TruncationResult should be falsy when not truncated."""
        result = TruncationResult(
            is_truncated=False,
            confidence=0.2,
            indicators=[],
            details={}
        )
        assert bool(result) is False


class TestTruncationError:
    """Tests for TruncationError exception."""
    
    def test_error_attributes(self):
        """TruncationError should store all attributes."""
        error = TruncationError(
            message="Test truncation",
            step_name="polish",
            input_length=10000,
            output_length=2000,
            truncation_indicators=["Unclosed code block"],
            original_input="Test input"
        )
        
        assert error.step_name == "polish"
        assert error.input_length == 10000
        assert error.output_length == 2000
        assert "Unclosed code block" in error.truncation_indicators
        assert error.original_input == "Test input"
    
    def test_error_str_includes_details(self):
        """TruncationError string representation should include details."""
        error = TruncationError(
            message="Test truncation",
            step_name="polish",
            input_length=10000,
            output_length=2000,
            truncation_indicators=["Unclosed code block"]
        )
        
        error_str = str(error)
        assert "polish" in error_str
        assert "10000" in error_str or "10,000" in error_str
        assert "2000" in error_str or "2,000" in error_str


class TestGetTruncationWarningMessage:
    """Tests for get_truncation_warning_message function."""
    
    def test_returns_empty_for_non_truncated(self):
        """Should return empty string for non-truncated result."""
        result = TruncationResult(
            is_truncated=False,
            confidence=0.1,
            indicators=[],
            details={}
        )
        message = get_truncation_warning_message(result)
        assert message == ""
    
    def test_includes_indicators_for_truncated(self):
        """Should include indicators in warning message."""
        result = TruncationResult(
            is_truncated=True,
            confidence=0.8,
            indicators=["Unclosed code block", "Mid-sentence ending"],
            details={"length_ratio": 0.2}
        )
        message = get_truncation_warning_message(result, step_name="polish")
        
        assert "TRUNCATION" in message
        assert "polish" in message
        assert "Unclosed code block" in message
        assert "Mid-sentence ending" in message


class TestEstimateDocumentSections:
    """Tests for estimate_document_sections function."""
    
    def test_extracts_markdown_headers(self):
        """Should extract section names from markdown headers."""
        doc = """
# Introduction
Some text

## Methods
More text

### Data Collection
Details

## Results
Findings
"""
        sections = estimate_document_sections(doc)
        assert "Introduction" in sections
        assert "Methods" in sections
        assert "Results" in sections
    
    def test_handles_empty_document(self):
        """Should return empty list for empty document."""
        sections = estimate_document_sections("")
        assert sections == []
    
    def test_handles_no_sections(self):
        """Should return empty list for document without sections."""
        doc = "Just some plain text without any headers or structure."
        sections = estimate_document_sections(doc)
        assert len(sections) == 0


class TestInferCodeLanguage:
    """Tests for infer_code_language function."""

    def test_detects_python(self):
        code = "def main():\n    self.value = 42\n    print('hello')"
        assert infer_code_language(code) == "python"

    def test_detects_typescript(self):
        code = (
            "import React from 'react';\n"
            "const App: React.FC = () => {\n"
            "  const [count, setCount] = useState<number>(0);\n"
            "  return <div>{count}</div>;\n"
            "};\n"
            "export default App;"
        )
        assert infer_code_language(code) == "typescript"

    def test_detects_typescript_via_type_annotations(self):
        code = (
            "interface Props {\n"
            "  name: string;\n"
            "  age: number;\n"
            "}\n"
            "export function greet(props: Props): string {\n"
            "  return `Hello ${props.name}`;\n"
            "}"
        )
        assert infer_code_language(code) == "typescript"

    def test_detects_javascript(self):
        code = (
            "import express from 'express';\n"
            "const app = express();\n"
            "export default app;"
        )
        assert infer_code_language(code) == "javascript"

    def test_detects_go(self):
        code = (
            "package main\n\n"
            "func main() {\n"
            '    fmt.Println("hello")\n'
            "}"
        )
        assert infer_code_language(code) == "go"

    def test_detects_rust(self):
        code = (
            "fn main() {\n"
            "    let mut v = vec![1, 2, 3];\n"
            '    println!("{:?}", v);\n'
            "}"
        )
        assert infer_code_language(code) == "rust"

    def test_returns_none_for_empty(self):
        assert infer_code_language("") is None
        assert infer_code_language("   ") is None

    def test_returns_none_for_ambiguous(self):
        assert infer_code_language("hello world") is None


class TestGetExpectedSectionsForCode:
    """Tests for get_expected_sections_for_code function."""

    def test_python_sections(self):
        code = "def foo():\n    self.x = 1"
        sections = get_expected_sections_for_code(code)
        assert sections is not None
        assert "def " in sections
        assert "class " in sections

    def test_typescript_sections(self):
        code = (
            "import React from 'react';\n"
            "const App: React.FC = () => <div />;\n"
            "export default App;"
        )
        sections = get_expected_sections_for_code(code)
        assert sections is not None
        assert "export " in sections
        assert "const " in sections
        assert "def " not in sections

    def test_returns_none_for_unknown(self):
        assert get_expected_sections_for_code("just some text") is None

    def test_tsx_not_flagged_as_truncated_with_python_sections(self):
        """Regression: TSX code should not reach the 0.7 workflow threshold.

        With the old hardcoded ``["def ", "class "]``, the missing-sections
        signal added +0.3 confidence on top of other heuristics, pushing
        confidence above the 0.7 LeadContractor threshold.  With language-aware
        sections the missing-sections penalty is reduced, keeping the total
        below 0.7.
        """
        tsx_code = (
            "import React, { useState } from 'react';\n"
            "import { AlertDialog } from '@/components/ui';\n\n"
            "export const MigrationQueue: React.FC = () => {\n"
            "  const [items, setItems] = useState<string[]>([]);\n"
            "  return (\n"
            "    <AlertDialog>\n"
            "      <div>{items.length} items</div>\n"
            "    </AlertDialog>\n"
            "  );\n"
            "};\n"
        )
        # With the old hardcoded ["def ", "class "], this would add +0.3
        # confidence for missing sections, risking a false positive.
        sections = get_expected_sections_for_code(tsx_code)
        assert sections is not None
        assert "def " not in sections

        result = detect_truncation(tsx_code, expected_sections=sections)
        # Confidence should stay below the 0.7 workflow threshold
        assert result.confidence < 0.7, (
            f"TSX code confidence {result.confidence:.2f} >= 0.7: {result.indicators}"
        )


class TestCodeMode:
    """Tests for code_mode parameter — skips text-oriented heuristics."""

    VALID_TS = (
        "import { createClient } from '@supabase/supabase-js';\n"
        "\n"
        "const supabase = createClient(\n"
        "  process.env.SUPABASE_URL!,\n"
        "  process.env.SUPABASE_KEY!\n"
        ");\n"
        "\n"
        "export async function seedCatalog(file: string): Promise<void> {\n"
        "  const data = await readCSV(file);\n"
        "  for (const row of data) {\n"
        '    await supabase.from("products").upsert(row);\n'
        "  }\n"
        '  console.log(`Seeded ${data.length} products`);\n'
        "}\n"
        "\n"
        "seedCatalog(process.argv[2]).catch(console.error);\n"
    )

    VALID_PYTHON = (
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "def main():\n"
        '    path = Path(sys.argv[1])\n'
        '    data = path.read_text(encoding="utf-8")\n'
        "    print(f'Read {len(data)} chars')\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )

    def test_valid_ts_not_flagged_in_code_mode(self):
        """Valid TypeScript should not be flagged as truncated in code_mode."""
        result = detect_truncation(self.VALID_TS, code_mode=True)
        assert not result.is_truncated, (
            f"Valid TS flagged as truncated: {result.indicators}"
        )
        assert result.confidence == 0.0

    def test_valid_ts_would_be_flagged_in_prose_mode(self):
        """Same TS triggers false positives without code_mode (the bug scenario)."""
        result = detect_truncation(self.VALID_TS, code_mode=False)
        # Mid-sentence and/or unclosed-string patterns should fire
        assert result.confidence > 0.0, (
            "Expected some heuristic hits on raw code in prose mode"
        )

    def test_valid_python_not_flagged_in_code_mode(self):
        """Valid Python should not be flagged as truncated in code_mode."""
        result = detect_truncation(self.VALID_PYTHON, code_mode=True)
        assert not result.is_truncated, (
            f"Valid Python flagged as truncated: {result.indicators}"
        )

    def test_code_mode_detects_unclosed_code_block_indicator(self):
        """code_mode still detects unclosed ``` markers (LLM wrapper artifacts)."""
        wrapped = "```typescript\n" + self.VALID_TS  # no closing ```
        result = detect_truncation(wrapped, code_mode=True)
        assert result.confidence >= 0.4
        assert any("code block" in i for i in result.indicators)

    def test_code_mode_detects_brace_imbalance_indicator(self):
        """code_mode detects significant brace imbalance."""
        truncated = (
            "function a() {\n"
            "  function b() {\n"
            "    function c() {\n"
            "      if (true) {\n"
            "        const x = 1;\n"
        )
        result = detect_truncation(truncated, code_mode=True)
        assert result.confidence >= 0.35
        assert any("brace" in i.lower() for i in result.indicators)

    def test_code_mode_flags_combined_structural_issues(self):
        """Multiple structural issues combine to cross the truncation threshold."""
        # Unclosed code block (0.4) + brace imbalance (0.35) = 0.75
        truncated = (
            "```typescript\n"
            "function a() {\n"
            "  function b() {\n"
            "    function c() {\n"
            "      if (true) {\n"
            "        const x = 1;\n"
        )
        result = detect_truncation(truncated, code_mode=True)
        assert result.is_truncated
        assert result.confidence >= 0.7

    def test_code_mode_tolerates_small_brace_imbalance(self):
        """Small imbalance (1-2) from braces in strings should not trigger."""
        code_with_string_brace = (
            'const msg = "Use {name} for greeting";\n'
            'const other = "another {placeholder}";\n'
            "export default msg;\n"
        )
        result = detect_truncation(code_with_string_brace, code_mode=True)
        assert not result.is_truncated, (
            f"Small brace imbalance in strings flagged: {result.indicators}"
        )

    def test_code_mode_skips_mid_sentence_check(self):
        """Code ending with semicolon should not trigger mid-sentence in code_mode."""
        code = 'console.log("done");'
        result = detect_truncation(code, code_mode=True)
        assert not any("Mid-sentence" in i for i in result.indicators)

    def test_code_mode_skips_truncation_patterns(self):
        """Unclosed-string/backtick patterns should not fire in code_mode."""
        code = (
            "const url = `https://example.com/${id}`;\n"
            'const name = "world";\n'
            "export default url;\n"
        )
        result = detect_truncation(code, code_mode=True)
        assert not any("Unclosed string" in i for i in result.indicators)
        assert not any("Unclosed inline code" in i for i in result.indicators)

    def test_code_mode_skips_markdown_checks(self):
        """Markdown structure checks should not fire in code_mode."""
        # Code that happens to contain pipe characters (like a template)
        code = (
            "const table = `| Name | Age |\\n| --- | --- |`;\n"
            "export default table;\n"
        )
        result = detect_truncation(code, code_mode=True)
        assert not any("table" in i.lower() for i in result.indicators)

    def test_empty_output_still_detected_in_code_mode(self):
        """Empty output is always detected regardless of mode."""
        result = detect_truncation("", code_mode=True)
        assert result.is_truncated
        assert result.confidence == 1.0


class TestAutoDetectCodeMode:
    """Tests that code_mode auto-detects from content when not explicitly set.

    This is the programmatic safeguard: callers don't need to remember to pass
    code_mode=True because detect_truncation() inspects its own input.  Any
    new call site added in the future gets the right behavior automatically.
    """

    # Representative samples from languages the SDK's drafters commonly produce.
    # These MUST never trigger truncation — if a heuristic change causes any
    # to fail, the change is introducing a false positive regression.

    SAMPLES = {
        "typescript": (
            "import { createClient } from '@supabase/supabase-js';\n"
            "\n"
            "const supabase = createClient(\n"
            "  process.env.SUPABASE_URL!,\n"
            "  process.env.SUPABASE_KEY!\n"
            ");\n"
            "\n"
            "export async function seedCatalog(file: string): Promise<void> {\n"
            "  const data = await readCSV(file);\n"
            "  for (const row of data) {\n"
            '    await supabase.from("products").upsert(row);\n'
            "  }\n"
            '  console.log(`Seeded ${data.length} products`);\n'
            "}\n"
            "\n"
            "seedCatalog(process.argv[2]).catch(console.error);\n"
        ),
        "python": (
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def main():\n"
            '    path = Path(sys.argv[1])\n'
            '    data = path.read_text(encoding="utf-8")\n'
            "    print(f'Read {len(data)} chars')\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        ),
        "tsx_component": (
            "import React, { useState } from 'react';\n"
            "import { AlertDialog } from '@/components/ui';\n\n"
            "interface Props {\n"
            "  items: string[];\n"
            "  onDelete: (id: string) => void;\n"
            "}\n\n"
            "export const MigrationQueue: React.FC<Props> = ({ items, onDelete }) => {\n"
            "  const [selected, setSelected] = useState<string | null>(null);\n"
            "  return (\n"
            "    <AlertDialog>\n"
            "      <div>{items.length} items</div>\n"
            "    </AlertDialog>\n"
            "  );\n"
            "};\n"
        ),
        "go": (
            "package main\n\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            ")\n\n"
            "func main() {\n"
            '    if len(os.Args) < 2 {\n'
            '        fmt.Fprintf(os.Stderr, "usage: %s <name>\\n", os.Args[0])\n'
            '        os.Exit(1)\n'
            "    }\n"
            '    fmt.Printf("Hello, %s!\\n", os.Args[1])\n'
            "}\n"
        ),
        "rust": (
            "use std::env;\n\n"
            "fn main() {\n"
            "    let args: Vec<String> = env::args().collect();\n"
            '    let name = args.get(1).map(|s| s.as_str()).unwrap_or("world");\n'
            '    println!("Hello, {}!", name);\n'
            "}\n"
        ),
    }

    def test_auto_detect_no_false_positives(self):
        """All representative code samples pass with default (auto-detect) mode."""
        for lang, code in self.SAMPLES.items():
            result = detect_truncation(code)  # No code_mode — auto-detect
            assert not result.is_truncated, (
                f"{lang}: auto-detect flagged valid code as truncated "
                f"(confidence={result.confidence:.0%}): {result.indicators}"
            )
            assert result.confidence == 0.0, (
                f"{lang}: expected 0% confidence, got {result.confidence:.0%}: "
                f"{result.indicators}"
            )

    def test_auto_detect_enables_code_mode(self):
        """Auto-detect sets code_mode=True for source code content."""
        result = detect_truncation(self.SAMPLES["typescript"])
        assert result.details.get("code_mode") is True

    def test_auto_detect_disables_code_mode_for_prose(self):
        """Auto-detect leaves code_mode=False for non-code content."""
        prose = (
            "# Document Title\n\n"
            "This is a complete document with proper structure.\n\n"
            "## Section 1\n\n"
            "Some content here.\n"
        )
        result = detect_truncation(prose)
        assert result.details.get("code_mode") is False

    def test_explicit_override_respected(self):
        """Explicit code_mode=False overrides auto-detection."""
        ts_code = self.SAMPLES["typescript"]
        # Auto-detect would enable code_mode, but explicit False forces prose mode
        result_auto = detect_truncation(ts_code)
        result_forced = detect_truncation(ts_code, code_mode=False)
        # Forced prose mode should produce higher confidence (false positive)
        assert result_forced.confidence >= result_auto.confidence

