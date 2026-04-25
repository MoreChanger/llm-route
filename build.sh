#!/bin/bash
# Cross-platform build script for LLM-ROUTE
# Supports Linux and macOS

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Detect platform
detect_platform() {
    case "$(uname -s)" in
        Linux*)     PLATFORM="Linux";;
        Darwin*)    PLATFORM="macOS";;
        *)          echo -e "${RED}Unsupported platform: $(uname -s)${NC}"; exit 1;;
    esac
    echo -e "${BLUE}Detected platform: ${PLATFORM}${NC}"
}

# Check PyInstaller installation
check_pyinstaller() {
    if ! python -c "import PyInstaller" 2>/dev/null; then
        echo -e "${YELLOW}PyInstaller not found, installing...${NC}"
        pip install pyinstaller
    fi
}

# Build for Linux
build_linux() {
    echo -e "${BLUE}Building for Linux...${NC}"

    # Check for GI dependencies
    if ! dpkg -l | grep -q "gir1.2-appindicator3"; then
        echo -e "${YELLOW}Warning: gir1.2-appindicator3 not installed.${NC}"
        echo -e "${YELLOW}System tray may not work. Install with:${NC}"
        echo -e "${YELLOW}  sudo apt-get install gir1.2-appindicator3-0.1${NC}"
    fi

    # Run PyInstaller
    pyinstaller build.spec --clean $DEBUG_FLAG

    # Set executable permission
    chmod +x dist/llm-route

    echo -e "${GREEN}Build complete: dist/llm-route${NC}"
}

# Build for macOS
build_macos() {
    echo -e "${BLUE}Building for macOS...${NC}"

    # Check for icon file
    if [ ! -f "icon.icns" ]; then
        echo -e "${YELLOW}Warning: icon.icns not found. The app bundle will use default icon.${NC}"
        echo -e "${YELLOW}To create an icns file from a PNG:${NC}"
        echo -e "${YELLOW}  mkdir icon.iconset${NC}"
        echo -e "${YELLOW}  sips -z 16 16     icon.png --out icon.iconset/icon_16x16.png${NC}"
        echo -e "${YELLOW}  sips -z 32 32     icon.png --out icon.iconset/icon_16x16@2x.png${NC}"
        echo -e "${YELLOW}  ... (repeat for all sizes)${NC}"
        echo -e "${YELLOW}  iconutil -c icns icon.iconset${NC}"
    fi

    # Run PyInstaller
    pyinstaller build.spec --clean $DEBUG_FLAG

    # Check if app bundle was created
    if [ -d "dist/LLM-ROUTE.app" ]; then
        echo -e "${GREEN}Build complete: dist/LLM-ROUTE.app${NC}"
        echo ""
        echo -e "${BLUE}To run the app:${NC}"
        echo -e "  open dist/LLM-ROUTE.app"
        echo ""
        echo -e "${BLUE}For code signing (optional):${NC}"
        echo -e "  codesign --deep --force --verify --verbose --sign \"Developer ID Application: Your Name\" dist/LLM-ROUTE.app"
    else
        echo -e "${GREEN}Build complete: dist/llm-route${NC}"
    fi
}

# Main
main() {
    DEBUG_FLAG=""

    # Parse arguments
    while [[ "$#" -gt 0 ]]; do
        case $1 in
            --clean) ;;
            --debug) DEBUG_FLAG="--debug";;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --clean    Clean build (default behavior)"
                echo "  --debug    Build with debug information"
                echo "  -h, --help Show this help message"
                exit 0
                ;;
            *) echo -e "${RED}Unknown parameter: $1${NC}"; exit 1;;
        esac
        shift
    done

    detect_platform
    check_pyinstaller

    # Build for detected platform
    case "$PLATFORM" in
        Linux)  build_linux;;
        macOS)  build_macos;;
    esac

    echo ""
    echo -e "${GREEN}Build successful!${NC}"
    echo -e "Output directory: ${BLUE}dist/${NC}"
}

main "$@"
