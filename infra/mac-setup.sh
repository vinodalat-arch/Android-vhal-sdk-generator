#!/usr/bin/env bash
# =============================================================================
# Mac Setup for VHAL SDK Generator (vanilla Mac — nothing pre-installed)
# =============================================================================
# Usage:
#   bash infra/mac-setup.sh
#
# Steps:
#   1. Xcode Command Line Tools (git, clang)
#   2. Homebrew
#   3. Java 17 (required by Android SDK)
#   4. Google Cloud SDK
#   5. Android SDK + automotive emulator image
#   6. Clone repo + Python venv + SDK extraction
#   7. Shell profile setup
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
elif [ "$ARCH" = "arm64" ]; then
    ANDROID_ABI="arm64-v8a"
else
    fail "Unsupported architecture: $ARCH"
fi

info "Detected architecture: $ARCH"

# ─────────────────────────────────────────────
# Step 1: Xcode Command Line Tools
# ─────────────────────────────────────────────
step "Step 1: Xcode Command Line Tools"

if xcode-select -p &>/dev/null; then
    info "Xcode CLI tools already installed."
else
    info "Installing Xcode Command Line Tools..."
    xcode-select --install
    warn "A dialog will appear — click 'Install' and wait for it to finish."
    warn "Then re-run this script: bash infra/mac-setup.sh"
    exit 0
fi

# ─────────────────────────────────────────────
# Step 2: Homebrew
# ─────────────────────────────────────────────
step "Step 2: Homebrew"

if command -v brew &>/dev/null; then
    info "Homebrew already installed."
else
    # Check common install location for Apple Silicon
    if [ "$ARCH" = "arm64" ] && [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        info "Homebrew found at /opt/homebrew."
    elif [ -f /usr/local/bin/brew ]; then
        eval "$(/usr/local/bin/brew shellenv)"
        info "Homebrew found at /usr/local."
    else
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        if [ "$ARCH" = "arm64" ] && [ -f /opt/homebrew/bin/brew ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
    fi
fi

# Verify brew works
command -v brew &>/dev/null || fail "Homebrew not found after install. Close terminal, reopen, and re-run this script."
info "Homebrew OK: $(brew --prefix)"

# ─────────────────────────────────────────────
# Step 3: Java 17 (needed by Android SDK tools)
# ─────────────────────────────────────────────
step "Step 3: Java 17"

brew install openjdk@17 2>/dev/null || true

# Link so macOS finds it
BREW_JAVA="$(brew --prefix openjdk@17)/libexec/openjdk.jdk"
if [ -d "$BREW_JAVA" ]; then
    sudo ln -sfn "$BREW_JAVA" /Library/Java/JavaVirtualMachines/openjdk-17.jdk 2>/dev/null || true
    export JAVA_HOME="$BREW_JAVA/Contents/Home"
    export PATH="$JAVA_HOME/bin:$PATH"
fi

# Verify Java works
if java -version 2>&1 | grep -q "17"; then
    info "Java 17 OK."
else
    fail "Java 17 not working. Try: brew reinstall openjdk@17"
fi

# ─────────────────────────────────────────────
# Step 4: Google Cloud SDK
# ─────────────────────────────────────────────
step "Step 4: Google Cloud SDK"

if command -v gcloud &>/dev/null; then
    info "gcloud already installed: $(gcloud version 2>/dev/null | head -1)"
else
    info "Installing Google Cloud SDK via Homebrew..."
    brew install --cask google-cloud-sdk 2>/dev/null || true

    # Source gcloud into current session
    BREW_PREFIX="$(brew --prefix)"
    for inc in "$BREW_PREFIX/share/google-cloud-sdk/path.zsh.inc" \
               "$BREW_PREFIX/share/google-cloud-sdk/path.bash.inc" \
               "$HOME/google-cloud-sdk/path.zsh.inc"; do
        if [ -f "$inc" ]; then
            source "$inc"
            break
        fi
    done
    info "gcloud installed."
fi

# Check auth
if ! gcloud auth print-identity-token &>/dev/null 2>&1; then
    warn "gcloud not authenticated. Run after this script completes:"
    warn "  gcloud auth login"
    warn "  gcloud config set project vhal-builder"
else
    info "gcloud authenticated."
fi

# ─────────────────────────────────────────────
# Step 5: Android SDK + Automotive Emulator
# ─────────────────────────────────────────────
step "Step 5: Android SDK + Automotive Emulator"

# Also install wget/python if missing
brew install python@3 wget 2>/dev/null || true

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

# Verify
adb version >/dev/null 2>&1 || fail "adb not found after SDK install"
emulator -version >/dev/null 2>&1 || fail "emulator not found after SDK install"
info "Android SDK OK — adb and emulator working."

# ─────────────────────────────────────────────
# Step 6: Clone Repo + Python Env
# ─────────────────────────────────────────────
step "Step 6: Clone Repo + Python Environment"

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
# Step 7: Shell Profile Setup
# ─────────────────────────────────────────────
step "Step 7: Shell Environment"

# Detect shell profile (Mac defaults to zsh)
if [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
    PROFILE="$HOME/.zshrc"
else
    PROFILE="$HOME/.bashrc"
fi

MARKER="# vhal-sdk-generator setup"

if ! grep -q "$MARKER" "$PROFILE" 2>/dev/null; then
    BREW_PREFIX="$(brew --prefix)"
    cat >> "$PROFILE" << ENVEOF

# vhal-sdk-generator setup
eval "\$($BREW_PREFIX/bin/brew shellenv)"
export JAVA_HOME="$BREW_JAVA/Contents/Home"
export ANDROID_HOME="\$HOME/android-sdk"
export PATH="\$JAVA_HOME/bin:\$ANDROID_HOME/cmdline-tools/latest/bin:\$ANDROID_HOME/platform-tools:\$ANDROID_HOME/emulator:\$PATH"
# Google Cloud SDK
if [ -f "$BREW_PREFIX/share/google-cloud-sdk/path.zsh.inc" ]; then
  source "$BREW_PREFIX/share/google-cloud-sdk/path.zsh.inc"
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
echo "  Java:        $(java -version 2>&1 | head -1)"
echo "  clang++:     $(clang++ --version 2>/dev/null | head -1)"
echo "  gcloud:      $(gcloud version 2>/dev/null | head -1 || echo 'installed (needs auth)')"
echo "  adb:         $(adb version 2>/dev/null | head -1)"
echo "  emulator:    $(emulator -version 2>/dev/null | head -1)"
echo "  vhal-gen:    $INSTALL_DIR/vhal-gen"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo "  1. Open a NEW terminal (so PATH takes effect), then:"
echo ""
echo "  2. Authenticate gcloud:"
echo "     gcloud auth login"
echo "     gcloud config set project vhal-builder"
echo ""
echo "  3. Start the emulator:"
echo "     emulator -avd automotive -writable-system -qemu -net user,hostfwd=udp::5555-:5555 &"
echo "     adb wait-for-device"
echo ""
echo "  4. Run Streamlit UI:"
echo "     cd $INSTALL_DIR/vhal-gen"
echo "     .venv/bin/python -m streamlit run streamlit_app/app.py"
echo ""
