#!/usr/bin/env bash
# Asta Resource Repository Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/allenai/asta-resource-repo/main/install.sh | bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default installation directory
INSTALL_DIR="${ASTA_INSTALL_DIR:-$HOME/.asta-resources}"

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║        Asta Resource Repository Installer                 ║"
echo "║        Lightweight Document Metadata Index                ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check if uv is installed
echo -e "${BLUE}[1/5]${NC} Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}uv not found. Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Try to source the shell config to make uv available
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi

    # Check again
    if ! command -v uv &> /dev/null; then
        echo -e "${RED}Failed to install uv. Please install manually:${NC}"
        echo -e "${YELLOW}  curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
        echo -e "${YELLOW}Then restart your terminal and run this installer again.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ uv installed successfully${NC}"
else
    echo -e "${GREEN}✓ uv is already installed${NC}"
fi

# Check Python version
echo -e "${BLUE}[2/5]${NC} Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.10"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    echo -e "${RED}Python 3.10+ is required. Found: $PYTHON_VERSION${NC}"
    echo -e "${YELLOW}Please install Python 3.10 or later and try again.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION is compatible${NC}"

# Clone or update repository
echo -e "${BLUE}[3/5]${NC} Installing Asta Resource Repository..."

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Installation directory already exists: $INSTALL_DIR${NC}"
    read -p "Update existing installation? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Updating repository...${NC}"
        cd "$INSTALL_DIR"
        git pull
        echo -e "${GREEN}✓ Repository updated${NC}"
    else
        echo -e "${YELLOW}Using existing installation${NC}"
    fi
else
    echo -e "${BLUE}Cloning repository to $INSTALL_DIR...${NC}"
    git clone https://github.com/allenai/asta-resource-repo.git "$INSTALL_DIR"
    echo -e "${GREEN}✓ Repository cloned${NC}"
fi

# Install dependencies
echo -e "${BLUE}[4/5]${NC} Installing dependencies..."
cd "$INSTALL_DIR"
uv sync --quiet
echo -e "${GREEN}✓ Dependencies installed${NC}"

# Test installation
echo -e "${BLUE}[5/5]${NC} Testing installation..."
if cd "$INSTALL_DIR" && uv run asta-index --help > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Installation successful!${NC}"
else
    echo -e "${YELLOW}⚠ Warning: Could not verify installation${NC}"
    echo -e "${YELLOW}  This might be normal. Try running manually:${NC}"
    echo -e "${YELLOW}    cd $INSTALL_DIR && uv run asta-index --help${NC}"
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "Installation directory: ${BLUE}$INSTALL_DIR${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo -e "${BLUE}1. Test the CLI:${NC}"
echo -e "   cd $INSTALL_DIR"
echo -e "   uv run asta-index --help"
echo ""
echo -e "${BLUE}2. Add your first document:${NC}"
echo -e "   uv run asta-index add https://example.com/doc.pdf \\"
echo -e "     --name=\"My Document\" \\"
echo -e "     --summary=\"Example document\" \\"
echo -e "     --tags=\"example\""
echo ""
echo -e "${BLUE}3. Configure MCP for Claude Code/Desktop:${NC}"
echo -e "   See: $INSTALL_DIR/MCP_SETUP.md"
echo ""
echo -e "   ${YELLOW}Quick config for Claude Code:${NC}"
echo -e "   Add this to your MCP configuration:"
echo ""
echo -e "${GREEN}   {${NC}"
echo -e "${GREEN}     \"mcpServers\": {${NC}"
echo -e "${GREEN}       \"asta-resources\": {${NC}"
echo -e "${GREEN}         \"command\": \"uv\",${NC}"
echo -e "${GREEN}         \"args\": [${NC}"
echo -e "${GREEN}           \"run\",${NC}"
echo -e "${GREEN}           \"--directory\",${NC}"
echo -e "${GREEN}           \"$INSTALL_DIR\",${NC}"
echo -e "${GREEN}           \"asta-resources-mcp\"${NC}"
echo -e "${GREEN}         ]${NC}"
echo -e "${GREEN}       }${NC}"
echo -e "${GREEN}     }${NC}"
echo -e "${GREEN}   }${NC}"
echo ""
echo -e "${BLUE}4. Read the documentation:${NC}"
echo -e "   README:       $INSTALL_DIR/README.md"
echo -e "   MCP Setup:    $INSTALL_DIR/MCP_SETUP.md"
echo ""
echo -e "${YELLOW}Optional:${NC} Add alias to your shell profile (~/.bashrc or ~/.zshrc):"
echo -e "   ${GREEN}alias asta-index='cd $INSTALL_DIR && uv run asta-index'${NC}"
echo ""
echo -e "Questions? Issues? Visit: ${BLUE}https://github.com/allenai/asta-resource-repo${NC}"
echo ""
