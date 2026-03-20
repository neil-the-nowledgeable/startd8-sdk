"""Tests for NodeLanguageProfile.generate_tsconfig() (REQ-PLI-NODE-P3)."""

import json

from startd8.languages.nodejs import NodeLanguageProfile


class TestGenerateTsconfig:
    def setup_method(self):
        self.profile = NodeLanguageProfile()

    def test_default_tsconfig(self):
        result = self.profile.generate_tsconfig()
        config = json.loads(result)
        opts = config["compilerOptions"]
        assert opts["target"] == "ES2022"
        assert opts["module"] == "NodeNext"
        assert opts["moduleResolution"] == "NodeNext"
        assert opts["strict"] is True
        assert opts["esModuleInterop"] is True
        assert opts["outDir"] == "./dist"
        assert config["include"] == ["src/**/*"]
        assert config["exclude"] == ["node_modules", "dist"]

    def test_custom_target_and_module(self):
        result = self.profile.generate_tsconfig(target="ES2020", module="CommonJS")
        config = json.loads(result)
        assert config["compilerOptions"]["target"] == "ES2020"
        assert config["compilerOptions"]["module"] == "CommonJS"

    def test_strict_mode_toggle(self):
        result = self.profile.generate_tsconfig(strict=False)
        config = json.loads(result)
        assert config["compilerOptions"]["strict"] is False

    def test_custom_out_dir(self):
        result = self.profile.generate_tsconfig(out_dir="./build")
        config = json.loads(result)
        assert config["compilerOptions"]["outDir"] == "./build"

    def test_valid_json_output(self):
        result = self.profile.generate_tsconfig()
        # Should not raise
        config = json.loads(result)
        assert isinstance(config, dict)
        # Should end with newline
        assert result.endswith("\n")

    def test_declaration_maps_enabled(self):
        result = self.profile.generate_tsconfig()
        config = json.loads(result)
        assert config["compilerOptions"]["declaration"] is True
        assert config["compilerOptions"]["declarationMap"] is True
        assert config["compilerOptions"]["sourceMap"] is True
