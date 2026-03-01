#!/usr/bin/env bash
# =============================================================================
# Ubuntu Laptop Setup for VHAL SDK Generator
# =============================================================================
# Installs everything needed to run vhal-gen (CLI + Streamlit), the Android
# Automotive emulator, and the GCP incremental build pipeline on a fresh
# Ubuntu 22.04+ installation.
#
# Usage:
#   bash infra/ubuntu-setup.sh
#
# What this script does:
#   1. Installs system packages (git, python3, clang, java, qemu-kvm)
#   2. Installs Google Cloud SDK (gcloud)
#   3. Installs Android SDK + automotive emulator image
#   4. Clones repo + creates Python venv
#   5. Verifies everything works
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
    LUNCH_TARGET="sdk_car_x86_64-trunk_staging-userdebug"
    PRODUCT_OUT="emulator_car_x86_64"
elif [ "$ARCH" = "aarch64" ]; then
    ANDROID_ABI="arm64-v8a"
    LUNCH_TARGET="sdk_car_arm64-trunk_staging-userdebug"
    PRODUCT_OUT="emulator_car64_arm64"
else
    fail "Unsupported architecture: $ARCH"
fi

info "Detected architecture: $ARCH → lunch target: $LUNCH_TARGET"

# ─────────────────────────────────────────────
# Step 1: System packages
# ─────────────────────────────────────────────
step "Step 1: System Packages"

sudo apt-get update -qq
sudo apt-get install -y -qq \
    git python3 python3-venv python3-pip \
    clang \
    openjdk-17-jdk-headless \
    wget unzip curl \
    qemu-kvm libvirt-daemon-system \
    adb

# KVM access for emulator
if [ ! -w /dev/kvm ] 2>/dev/null; then
    sudo adduser "$USER" kvm 2>/dev/null || true
    warn "Added $USER to kvm group — you may need to log out/in for it to take effect."
fi

info "System packages installed."

# ─────────────────────────────────────────────
# Step 2: Google Cloud SDK
# ─────────────────────────────────────────────
step "Step 2: Google Cloud SDK"

if command -v gcloud &>/dev/null; then
    info "gcloud already installed: $(gcloud version 2>/dev/null | head -1)"
else
    info "Installing Google Cloud SDK..."
    curl -sS https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/google-cloud-cli-linux-x86_64.tar.gz \
        -o /tmp/gcloud-sdk.tar.gz
    tar -xf /tmp/gcloud-sdk.tar.gz -C "$HOME"
    "$HOME/google-cloud-sdk/install.sh" --quiet --path-update true
    export PATH="$HOME/google-cloud-sdk/bin:$PATH"
    rm /tmp/gcloud-sdk.tar.gz
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
    CMDTOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
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
sdkmanager --install \
    "platform-tools" \
    "emulator" \
    "platforms;android-34" \
    "system-images;android-34;android-automotive;x86_64"

# Create AVD if not exists
if ! avdmanager list avd 2>/dev/null | grep -q "Name: automotive"; then
    info "Creating automotive AVD..."
    echo "no" | avdmanager create avd \
        -n automotive \
        -k "system-images;android-34;android-automotive;x86_64" \
        -d "automotive_1024p_landscape" \
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

PROFILE="$HOME/.bashrc"
MARKER="# vhal-sdk-generator setup"

if ! grep -q "$MARKER" "$PROFILE" 2>/dev/null; then
    cat >> "$PROFILE" << 'ENVEOF'

# vhal-sdk-generator setup
export ANDROID_HOME="$HOME/android-sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$ANDROID_HOME/emulator:$HOME/google-cloud-sdk/bin:$PATH"
ENVEOF
    info "Added environment variables to $PROFILE"
else
    info "Environment variables already in $PROFILE"
fi

# ─────────────────────────────────────────────
# Step 6: Architecture Check for GCP
# ─────────────────────────────────────────────
step "Step 6: GCP Build Target Check"

if [ "$ARCH" = "x86_64" ]; then
    warn "This laptop is x86_64 but GCP currently builds ARM64 binaries."
    warn "The GCP lunch target must be changed for x86_64 emulator compatibility."
    warn ""
    warn "One-time GCP setup required:"
    warn "  1. SSH to GCP:  gcloud compute ssh aosp-builder --zone=us-central1-a"
    warn "  2. Run:         cd /aosp && source build/envsetup.sh"
    warn "  3. Run:         lunch sdk_car_x86_64-trunk_staging-userdebug"
    warn "  4. First build: m -j\$(nproc)  (this takes ~2-4 hours the first time)"
    warn ""
    warn "After that, update vhal-gen config in:"
    warn "  $INSTALL_DIR/vhal-gen/vhal_gen/pipeline/config.py"
    warn "  Change DEFAULT_LUNCH_TARGET to: sdk_car_x86_64-trunk_staging-userdebug"
    warn "  Change GCP_PRODUCT_OUT_PATH to: ~/aosp/out/target/product/emulator_car_x86_64"
else
    info "ARM64 laptop — matches current GCP build target. No changes needed."
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
echo "  1. Log out and back in (for KVM access)"
echo ""
echo "  2. Authenticate gcloud (if not already):"
echo "     gcloud auth login"
echo "     gcloud config set project vhal-builder"
echo ""
echo "  3. Start the emulator (with UDP port forwarding for VSM Ethernet):"
echo "     emulator -avd automotive -writable-system -qemu -net user,hostfwd=udp::5555-:5555 &"
echo "     adb wait-for-device"
echo ""
echo "  4. Run Streamlit UI:"
echo "     cd $INSTALL_DIR/vhal-gen"
echo "     .venv/bin/python -m streamlit run streamlit_app/app.py"
echo ""
echo "  5. Or use CLI:"
echo "     cd $INSTALL_DIR/vhal-gen"
echo "     .venv/bin/python -m vhal_gen generate --help"
echo ""

if [ "$ARCH" = "x86_64" ]; then
    echo -e "  ${YELLOW}6. IMPORTANT: Switch GCP to x86_64 (see Step 6 warnings above)${NC}"
    echo ""
fi
