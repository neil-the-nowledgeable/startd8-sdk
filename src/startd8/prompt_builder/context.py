"""
Project Context - Detect project structure and suggest variable values
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import os

from .config import PROMPT_BUILDER_CONFIG


class ProjectContext:
    """Detect project context and suggest variable values"""
    
    # Common directories to skip when scanning
    SKIP_DIRS = {
        'node_modules', '__pycache__', 'venv', '.venv', 'env', '.env',
        '.git', '.hg', '.svn', 'dist', 'build', 'target', '.idea', 
        '.vscode', '.pytest_cache', '.mypy_cache', 'coverage', '.tox',
        'eggs', '*.egg-info', '.eggs'
    }
    
    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize project context.
        
        Args:
            project_path: Path to project directory. Defaults to current working directory.
        """
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self._structure: Dict[str, Any] = {}
        self._project_type: Optional[str] = None
        self._files_list: List[str] = []
        self._dirs_list: List[str] = []
    
    def scan_directory(self, max_depth: int = None) -> Dict[str, Any]:
        """
        Scan project directory structure.
        Returns nested dict of directories and files.
        """
        if max_depth is None:
            max_depth = PROMPT_BUILDER_CONFIG["max_dir_scan_depth"]
        
        self._structure = self._scan_recursive(self.project_path, max_depth)
        return self._structure
    
    def _scan_recursive(self, path: Path, depth: int) -> Dict[str, Any]:
        """Recursively scan directory"""
        if depth <= 0 or not path.is_dir():
            return {}
        
        result = {
            "_type": "directory",
            "_files": [],
            "_dirs": []
        }
        
        try:
            for item in sorted(path.iterdir()):
                # Skip hidden files and common ignore patterns
                if item.name.startswith('.'):
                    continue
                if item.name in self.SKIP_DIRS:
                    continue
                if any(item.name.endswith(skip.replace('*', '')) for skip in self.SKIP_DIRS if '*' in skip):
                    continue
                
                if item.is_file():
                    result["_files"].append(item.name)
                    self._files_list.append(str(item.relative_to(self.project_path)))
                elif item.is_dir():
                    result["_dirs"].append(item.name)
                    self._dirs_list.append(item.name)
                    result[item.name] = self._scan_recursive(item, depth - 1)
        except PermissionError:
            pass
        
        return result
    
    def detect_project_type(self) -> Optional[str]:
        """Detect project type based on indicator files"""
        if self._project_type:
            return self._project_type
        
        indicators = PROMPT_BUILDER_CONFIG["project_indicators"]
        
        for project_type, files in indicators.items():
            for indicator_file in files:
                if (self.project_path / indicator_file).exists():
                    self._project_type = project_type
                    return project_type
        
        return None
    
    def get_main_files(self) -> List[str]:
        """Get list of main/entry point files"""
        main_patterns = [
            'main.py', 'app.py', '__main__.py', 'index.py',
            'main.ts', 'index.ts', 'app.ts',
            'main.js', 'index.js', 'app.js',
            'main.go', 'main.rs', 'Main.java'
        ]
        
        found = []
        for pattern in main_patterns:
            if (self.project_path / pattern).exists():
                found.append(pattern)
            # Check in src/
            if (self.project_path / 'src' / pattern).exists():
                found.append(f'src/{pattern}')
        
        return found
    
    def suggest_values(self) -> Dict[str, str]:
        """
        Generate suggested values for common template variables.
        Based on project directory analysis.
        """
        suggestions = {}
        
        # Always suggest project path
        suggestions["PROJECT_PATH"] = str(self.project_path)
        suggestions["PATH"] = str(self.project_path)
        
        # Project name from directory
        suggestions["PROJECT_NAME"] = self.project_path.name
        
        # Detect language/type
        project_type = self.detect_project_type()
        if project_type:
            suggestions["LANGUAGE"] = project_type.capitalize()
            suggestions["PROJECT_TYPE"] = project_type
            suggestions["TARGET_LANGUAGE"] = project_type.capitalize()
        
        # Scan structure if not done
        if not self._structure:
            self.scan_directory()
        
        # Suggest source directory
        common_src_dirs = ['src', 'lib', 'app', 'source', 'pkg']
        for src_dir in common_src_dirs:
            if src_dir in self._structure.get("_dirs", []):
                suggestions["SOURCE_DIR"] = src_dir
                suggestions["SRC_DIR"] = src_dir
                break
        
        # Count files for context
        root_files = self._structure.get("_files", [])
        root_dirs = self._structure.get("_dirs", [])
        suggestions["FILE_COUNT"] = str(len(root_files))
        suggestions["DIR_COUNT"] = str(len(root_dirs))
        
        # Get main files
        main_files = self.get_main_files()
        if main_files:
            suggestions["MAIN_FILE"] = main_files[0]
        
        # Try to get package/project name from config files
        self._extract_name_from_config(suggestions)
        
        return suggestions
    
    def _extract_name_from_config(self, suggestions: Dict[str, str]) -> None:
        """Try to extract project name from config files"""
        # Python: setup.py, pyproject.toml
        setup_py = self.project_path / "setup.py"
        if setup_py.exists():
            try:
                content = setup_py.read_text()
                if 'name=' in content:
                    # Simple extraction - not perfect but good enough
                    import re
                    match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                    if match:
                        suggestions["PACKAGE_NAME"] = match.group(1)
            except Exception:
                pass
        
        # Node.js: package.json
        package_json = self.project_path / "package.json"
        if package_json.exists():
            try:
                import json
                data = json.loads(package_json.read_text())
                if 'name' in data:
                    suggestions["PACKAGE_NAME"] = data['name']
                if 'description' in data:
                    suggestions["PROJECT_DESCRIPTION"] = data['description']
            except Exception:
                pass
    
    def get_directory_tree(self, max_depth: int = 2) -> str:
        """Get a text representation of the directory tree"""
        if not self._structure:
            self.scan_directory(max_depth)
        
        lines = [f"{self.project_path.name}/"]
        self._build_tree_lines(self._structure, "", lines, max_depth)
        return "\n".join(lines)
    
    def _build_tree_lines(
        self, 
        structure: Dict[str, Any], 
        prefix: str, 
        lines: List[str],
        depth: int
    ) -> None:
        """Build tree representation lines"""
        if depth <= 0:
            return
        
        dirs = structure.get("_dirs", [])
        files = structure.get("_files", [])
        
        # Add directories
        for i, d in enumerate(dirs):
            is_last_dir = (i == len(dirs) - 1) and not files
            connector = "└── " if is_last_dir else "├── "
            lines.append(f"{prefix}{connector}{d}/")
            
            # Recurse into subdirectory
            if d in structure:
                new_prefix = prefix + ("    " if is_last_dir else "│   ")
                self._build_tree_lines(structure[d], new_prefix, lines, depth - 1)
        
        # Add files
        for i, f in enumerate(files):
            is_last = (i == len(files) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{f}")

