# sift-printer

A tiny Python client for streaming **MQTT telemetry** from Bambu Lab 3D printers via Bambu's cloud broker. Useful for pulling real-time printer state (temps, progress, fan speeds, errors, HMS codes, AMS info, etc.) into a telemetry pipeline.

Built on top of Bambu's (undocumented) cloud API and MQTT broker at `us.mqtt.bambulab.com:8883`.

## Install

```bash
pip install git+https://github.com/weiqlu/sift-printer.git
```

## Quickstart

```python
from bambu import BambuPrinter

# One-time login flow to get an access token.
BambuPrinter.send_verification_code("you@example.com")
code = input("Enter verification code from email: ")
tokens = BambuPrinter.login_with_code("you@example.com", code)

# Connect and stream reports.
printer = BambuPrinter(tokens["accessToken"])
printer.on_report(lambda r: print(r))
printer.connect()

# Control commands.
printer.set_light(False)
# printer.pause() / printer.resume() / printer.stop()
```

The printer pushes a full-state snapshot on every (re)connect, followed by deltas as state changes. Merge deltas into a running state object if you need complete state at any given moment.

## Auth notes

- Access tokens last ~90 days; use the `refreshToken` from login to mint a new one without re-entering a code.
- The verification code flow requires access to the email on the Bambu account.
