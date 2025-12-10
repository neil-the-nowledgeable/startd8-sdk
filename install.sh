#!/bin/bash
# Installation script for startd8
# Supports both pipx (recommended) and standard pip installation

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_METHOD="${1:-pipx}"

echo "🚀 Installing startd8..."
echo ""

if [ "$INSTALL_METHOD" = "pipx" ]; then
    echo "📦 Using pipx (recommended - isolated environment)"
    echo ""
    
    # Check if pipx is installed
    if ! command -v pipx &> /dev/null; then
        echo "❌ pipx is not installed."
        echo ""
        echo "Install pipx first:"
        echo "  macOS:  brew install pipx"
        echo "  Linux:  pip install --user pipx"
        echo "  Then:   pipx ensurepath"
        echo ""
        exit 1
    fi
    
    echo "✅ pipx found: $(which pipx)"
    echo ""
    echo "Installing startd8 in isolated environment..."
    pipx install -e "$SCRIPT_DIR"
    
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "Usage:"
    echo "  startd8 --help"
    echo "  startd8 tui"
    echo ""
    echo "To update:"
    echo "  pipx upgrade startd8"
    echo ""
    echo "To uninstall:"
    echo "  pipx uninstall startd8"
    
elif [ "$INSTALL_METHOD" = "pip" ]; then
    echo "📦 Using standard pip installation"
    echo ""
    echo "⚠️  Note: This installs into your current Python environment."
    echo "   Consider using a virtual environment to avoid conflicts."
    echo ""
    
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    
    echo "Installing startd8..."
    pip install -e "$SCRIPT_DIR"
    
    echo ""
    echo "✅ Installation complete!"
    echo ""
    echo "Usage:"
    echo "  startd8 --help"
    echo "  startd8 tui"
    
else
    echo "Usage: $0 [pipx|pip]"
    echo ""
    echo "  pipx  - Install with pipx (recommended, isolated environment)"
    echo "  pip   - Install with standard pip"
    echo ""
    exit 1
fi

