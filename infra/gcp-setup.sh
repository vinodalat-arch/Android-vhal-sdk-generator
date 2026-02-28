#!/usr/bin/env bash
# Create a GCP VM suitable for building AOSP VHAL modules.
#
# Prerequisites:
#   - gcloud CLI authenticated (`gcloud auth login`)
#   - A GCP project selected (`gcloud config set project <PROJECT>`)
#
# Usage:
#   bash infra/gcp-setup.sh [INSTANCE_NAME] [ZONE]
#
# The VM will be created with:
#   - n2-standard-16 (16 vCPU, 64 GB RAM)
#   - 500 GB SSD persistent disk
#   - Ubuntu 22.04 LTS
#
# After creation the script SSHs in and installs build dependencies
# (repo, git-lfs, JDK, etc.) then sets up the GitHub Actions self-hosted
# runner.  You still need to supply a runner token — the script will
# prompt for it.

set -euo pipefail

INSTANCE="${1:-aosp-builder}"
ZONE="${2:-us-central1-a}"
MACHINE_TYPE="n2-standard-16"
DISK_SIZE="500GB"
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

echo "==> Creating VM: ${INSTANCE} in ${ZONE}"
gcloud compute instances create "${INSTANCE}" \
    --zone="${ZONE}" \
    --machine-type="${MACHINE_TYPE}" \
    --boot-disk-size="${DISK_SIZE}" \
    --boot-disk-type=pd-ssd \
    --image-family="${IMAGE_FAMILY}" \
    --image-project="${IMAGE_PROJECT}" \
    --scopes=cloud-platform \
    --tags=aosp-builder

echo "==> Waiting for SSH to become available..."
gcloud compute ssh "${INSTANCE}" --zone="${ZONE}" --command="echo 'SSH ready'"

echo "==> Installing build dependencies..."
gcloud compute ssh "${INSTANCE}" --zone="${ZONE}" -- bash -s <<'REMOTE'
set -euo pipefail

sudo apt-get update
sudo apt-get install -y \
    git git-lfs curl unzip zip \
    openjdk-17-jdk \
    python3 python3-pip \
    build-essential \
    rsync \
    libncurses5 \
    libxml2-utils \
    xsltproc \
    flex bison \
    zlib1g-dev \
    libssl-dev

# Install repo tool
if ! command -v repo &>/dev/null; then
    sudo curl -o /usr/local/bin/repo \
        https://storage.googleapis.com/git-repo-downloads/repo
    sudo chmod +x /usr/local/bin/repo
fi

# Configure git
git config --global user.email "aosp-builder@flync.io"
git config --global user.name "AOSP Builder"
git config --global color.ui false

# Create AOSP workspace
sudo mkdir -p /aosp
sudo chown "$(id -un):$(id -gn)" /aosp

echo "==> Dependencies installed."
echo "==> Next step: run  infra/aosp-sync.sh  on this VM to sync AOSP sources."
echo "==> Then install GitHub Actions self-hosted runner:"
echo "    https://github.com/<OWNER>/<REPO>/settings/actions/runners/new"
REMOTE

echo "==> VM ${INSTANCE} is ready."
echo "    SSH: gcloud compute ssh ${INSTANCE} --zone=${ZONE}"
