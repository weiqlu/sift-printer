# sift-printer

A Python client that connects to Bambu Lab printers through their MQTT broker. Stream real-time printer state (temps, progress, fans, errors, AMS, etc.) and send control commands from the same session.

## Caveats

- Not affiliated with Bambu Lab.
- Cloud only. No LAN support.
- Uses reverse-engineered endpoints that can break without warning.
- Only tested on the Bambu P1S.

## Install

```bash
pip install git+https://github.com/weiqlu/sift-printer.git
```

Access tokens last ~90 days. Use `tokens["refreshToken"]` to renew without another code.
