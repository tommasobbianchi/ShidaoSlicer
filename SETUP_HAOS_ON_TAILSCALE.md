# Protocol: HAOS Tailscale Integration

> **Objective:** Connect Home Assistant OS (HAOS) from the Client network to the Antigravity Swarm (Tailscale) to enable remote configuration by the Agent.

## Phase 1: Join the Swarm (User Action)

Since HAOS is on your local network, you must initiate the connection:

1.  **Access Home Assistant**: Go to `http://homeassistant.local:8123` (or your local IP).
2.  **Install Tailscale**:
    *   Navigate to **Settings** > **Add-ons** > **Add-on Store**.
    *   Search for **"Tailscale"**.
    *   Click **Install**.
3.  **Configure & Start**:
    *   Enable **"Start on boot"** and **"Watchdog"**.
    *   Click **Start**.
    *   Check the **Log** tab giving it a few seconds. It will show a login URL (e.g., `https://login.tailscale.com/a/...`).
    *   **Copy & Visit** that URL to authenticate HAOS into your tailnet.

## Phase 2: Enable Remote Control (SSH)

For Antigravity to configure HAOS, we need SSH access via Tailscale.

1.  In Add-on Store, install **"Terminal & SSH"** (official) or "SSH & Web Terminal" (community).
2.  **Configuration**:
    *   Set a complex `password` or add your public key (preferred).
    *   Network Port: `22` (default).
3.  **Start** the Add-on.

## Phase 3: Verification

Once Phase 1 & 2 are complete, tell Antigravity execution is done.
I will then verify visibility:

```bash
# Antigravity will run:
tailscale ping <haos-hostname>
ssh root@<haos-ip-on-tailscale>
```
