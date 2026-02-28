# Infrastructure: GCP AOSP Builder

One-time setup for a GCP VM that builds AOSP VHAL modules as a GitHub Actions self-hosted runner.

## Prerequisites

- `gcloud` CLI authenticated with a GCP project
- GitHub repo with Actions enabled
- A GitHub personal access token or runner registration token

## Setup Steps

### 1. Create the GCP VM

```bash
bash infra/gcp-setup.sh [INSTANCE_NAME] [ZONE]
# Defaults: aosp-builder, us-central1-a
```

This creates an `n2-standard-16` VM (16 vCPU, 64 GB RAM, 500 GB SSD) with Ubuntu 22.04 and installs all AOSP build dependencies.

### 2. Sync AOSP Sources (on the VM)

```bash
gcloud compute ssh aosp-builder --zone=us-central1-a
bash /path/to/infra/aosp-sync.sh [AOSP_TAG] [AOSP_DIR]
# Defaults: android-14.0.0_r75, /aosp
```

Performs a selective sync (~80 GB) of only the repos needed to build VHAL modules.

### 3. Install GitHub Actions Runner (on the VM)

Follow: `https://github.com/<OWNER>/<REPO>/settings/actions/runners/new`

Choose **Linux x64**, then on the VM:

```bash
mkdir ~/actions-runner && cd ~/actions-runner
curl -o actions-runner-linux-x64.tar.gz -L <DOWNLOAD_URL>
tar xzf actions-runner-linux-x64.tar.gz
./config.sh --url https://github.com/<OWNER>/<REPO> --token <TOKEN> --labels aosp-builder
sudo ./svc.sh install
sudo ./svc.sh start
```

The runner should appear in **Settings > Actions > Runners** with label `aosp-builder`.

### 4. Verify

Trigger the workflow from GitHub UI: **Actions > Build VHAL > Run workflow**.

## Emulator Setup (local machine)

The `deploy-test` pipeline pushes built binaries to a running automotive emulator. Set it up once:

```bash
# Install Android SDK command-line tools, then:
sdkmanager "system-images;android-14;google_apis;x86_64"
avdmanager create avd -n automotive -k "system-images;android-14;google_apis;x86_64" -d "automotive_1024p_landscape"
emulator -avd automotive -no-snapshot &

# Wait for boot, then verify:
adb wait-for-device
adb shell getprop ro.build.display.id
```

The pipeline checks `adb devices` before deploying — it does **not** manage the emulator lifecycle.

## Cost Estimate

| Resource | Spec | ~Cost/month (idle) |
|----------|------|--------------------|
| VM | n2-standard-16 | ~$390 (running 24/7) |
| Disk | 500 GB SSD | ~$85 |

Recommendation: stop the VM when not building (`gcloud compute instances stop aosp-builder`).
