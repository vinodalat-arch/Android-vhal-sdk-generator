#!/usr/bin/env bash
# =============================================================================
# Mac Setup for VHAL SDK Generator
# =============================================================================
# Installs everything needed to run vhal-gen (CLI + Streamlit), the Android
# Automotive emulator, and the GCP incremental build pipeline on macOS.
#
# Usage:
#   bash infra/mac-setup.sh
#
# What this script does:
#   1. Installs Homebrew packages (python3, java, clang)
#   2. Installs Google Cloud SDK
#   3. Installs Android SDK + automotive emulator image
#   4. Clones repo + creates Python venv
#   5. Sets up shell environment
# =============================================================================
set -euo pipefail

REPO_URL="${VHAL_REPO_URL:-https://github.com/vinodalat-arch/Android-vhal-sdk-generator.git}"
INSTALL_DIR="${VHAL_INSTALL_DIR:-$HOME/vhal-sdk-generator}"
ANDROID_HOME="${ANDROID_HOME:-$HOME/android-sdk}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }
step()  { echo -e "\n${BOLD}=== $* ===${NC}"; }

# Detect architecture
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then
    ANDROID_ABI="x86_64"
    CMDTOOLS_SUFFIX="mac"
elif [ "$ARCH" = "arm64" ]; then
    ANDROID_ABI="arm64-v8a"
    CMDTOOLS_SUFFIX="mac"
else
    fail "Unsupported architecture: $ARCH"
fi

info "Detected architecture: $ARCH"

# ─────────────────────────────────────────────
# Step 1: Homebrew + System Packages
# ─────────────────────────────────────────────
step "Step 1: Homebrew + System Packages"

if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to path for Apple Silicon
    if [ "$ARCH" = "arm64" ] && [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    info "Homebrew already installed."
fi

brew install python@3 openjdk@17 wget 2>/dev/null || true

# clang comes with Xcode Command Line Tools
if ! command -v clang++ &>/dev/null; then
    info "Installing Xcode Command Line Tools..."
    xcode-select --install 2>/dev/null || true
    warn "If prompted, click 'Install' in the dialog and wait for it to finish."
    warn "Then re-run this script."
fi

info "System packages installed."

# ─────────────────────────────────────────────
# Step 2: Google Cloud SDK
# ─────────────────────────────────────────────
step "Step 2: Google Cloud SDK"

if command -v gcloud &>/dev/null; then
    info "gcloud already installed: $(gcloud version 2>/dev/null | head -1)"
else
    info "Installing Google Cloud SDK via Homebrew..."
    brew install --cask google-cloud-sdk 2>/dev/null || true
    # Source gcloud paths
    if [ -f "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc" ]; then
        source "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc"
    elif [ -f "$HOME/google-cloud-sdk/path.bash.inc" ]; then
        source "$HOME/google-cloud-sdk/path.bash.inc"
    fi
    info "gcloud installed."
fi

# Check auth
if ! gcloud auth print-identity-token &>/dev/null; then
    warn "gcloud not authenticated. Run after this script completes:"
    warn "  gcloud auth login"
    warn "  gcloud config set project vhal-builder"
else
    info "gcloud authenticated."
fi

# ─────────────────────────────────────────────
# Step 3: Android SDK + Automotive Emulator
# ─────────────────────────────────────────────
step "Step 3: Android SDK + Automotive Emulator"

mkdir -p "$ANDROID_HOME"

# Download command-line tools if not present
if [ ! -d "$ANDROID_HOME/cmdline-tools/latest" ]; then
    info "Downloading Android SDK command-line tools..."
    CMDTOOLS_URL="https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip"
    wget -q "$CMDTOOLS_URL" -O /tmp/cmdline-tools.zip
    mkdir -p "$ANDROID_HOME/cmdline-tools"
    unzip -q /tmp/cmdline-tools.zip -d "$ANDROID_HOME/cmdline-tools"
    mv "$ANDROID_HOME/cmdline-tools/cmdline-tools" "$ANDROID_HOME/cmdline-tools/latest"
    rm /tmp/cmdline-tools.zip
fi

export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"

# Accept licenses
yes | sdkmanager --licenses >/dev/null 2>&1 || true

# Install required packages
info "Installing Android SDK packages (this may take a few minutes)..."
SYSTEM_IMAGE="system-images;android-34-ext9;android-automotive;${ANDROID_ABI}"

sdkmanager --install \
    "platform-tools" \
    "emulator" \
    "platforms;android-34" \
    "$SYSTEM_IMAGE"

# Create AVD if not exists
if ! avdmanager list avd 2>/dev/null | grep -q "Name: automotive"; then
    info "Creating automotive AVD..."
    echo "no" | avdmanager create avd \
        -n automotive \
        -k "$SYSTEM_IMAGE" \
        --force
    info "AVD 'automotive' created."
else
    info "AVD 'automotive' already exists."
fi

# ─────────────────────────────────────────────
# Step 4: Clone Repo + Python Env
# ─────────────────────────────────────────────
step "Step 4: Clone Repo + Python Environment"

if [ -d "$INSTALL_DIR/vhal-gen" ]; then
    info "Repo already cloned at $INSTALL_DIR"
    cd "$INSTALL_DIR/vhal-gen"
    git pull --ff-only || warn "git pull failed — you may have local changes"
else
    info "Cloning repo to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR/vhal-gen"
fi

# Extract Vehicle Body SDK from reference archive
if [ ! -d "$INSTALL_DIR/performance-stack-Body-lighting-Draft" ]; then
    if [ -f "$INSTALL_DIR/reference/vehicle-body-sdk.tar.gz" ]; then
        info "Extracting Vehicle Body SDK..."
        tar xzf "$INSTALL_DIR/reference/vehicle-body-sdk.tar.gz" -C "$INSTALL_DIR"
        info "SDK extracted to $INSTALL_DIR/performance-stack-Body-lighting-Draft/src/"
    else
        warn "Vehicle Body SDK archive not found at reference/vehicle-body-sdk.tar.gz"
    fi
else
    info "Vehicle Body SDK already extracted."
fi

if [ ! -d ".venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv .venv
fi

info "Installing Python dependencies..."
.venv/bin/pip install -q -e .

# ─────────────────────────────────────────────
# Step 5: Shell Profile Setup
# ─────────────────────────────────────────────
step "Step 5: Shell Environment"

# Detect shell profile
if [ -n "${ZSH_VERSION:-}" ] || [ "$SHELL" = "$(which zsh)" ]; then
    PROFILE="$HOME/.zshrc"
else
    PROFILE="$HOME/.bashrc"
fi

MARKER="# vhal-sdk-generator setup"

if ! grep -q "$MARKER" "$PROFILE" 2>/dev/null; then
    cat >> "$PROFILE" << 'ENVEOF'

# vhal-sdk-generator setup
export ANDROID_HOME="$HOME/android-sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$PATH"
# Google Cloud SDK
if [ -f "$(brew --prefix 2>/dev/null)/share/google-cloud-sdk/path.zsh.inc" ]; then
  source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"
elif [ -f "$(brew --prefix 2>/dev/null)/share/google-cloud-sdk/path.bash.inc" ]; then
  source "$(brew --prefix)/share/google-cloud-sdk/path.bash.inc"
elif [ -f "$HOME/google-cloud-sdk/path.zsh.inc" ]; then
  source "$HOME/google-cloud-sdk/path.zsh.inc"
fi
ENVEOF
    info "Added environment variables to $PROFILE"
else
    info "Environment variables already in $PROFILE"
fi

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────
step "Setup Complete"

echo ""
echo -e "${BOLD}Installed:${NC}"
echo "  Python:      $(python3 --version)"
echo "  clang++:     $(clang++ --version 2>/dev/null | head -1)"
echo "  gcloud:      $(gcloud version 2>/dev/null | head -1 || echo 'installed (needs auth)')"
echo "  adb:         $(adb version 2>/dev/null | head -1 || echo 'installed')"
echo "  vhal-gen:    $INSTALL_DIR/vhal-gen"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo "  1. Authenticate gcloud (if not already):"
echo "     gcloud auth login"
echo "     gcloud config set project vhal-builder"
echo ""
echo "  2. Start the emulator (with UDP port forwarding for VSM Ethernet):"
echo "     emulator -avd automotive -writable-system -qemu -net user,hostfwd=udp::5555-:5555 &"
echo "     adb wait-for-device"
echo ""
echo "  3. Run Streamlit UI:"
echo "     cd $INSTALL_DIR/vhal-gen"
echo "     .venv/bin/python -m streamlit run streamlit_app/app.py"
echo ""
echo "  4. Or use CLI:"
echo "     cd $INSTALL_DIR/vhal-gen"
echo "     .venv/bin/python -m vhal_gen generate --help"
echo ""
