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

## Usage

```python
from bambu import BambuPrinter

BambuPrinter.send_verification_code("you@example.com")
code = input("Code from email: ")
tokens = BambuPrinter.login_with_code("you@example.com", code)

printer = BambuPrinter(tokens["accessToken"])
printer.on_report(lambda r: print(r))
printer.connect()
printer.set_light(False)
```

Access tokens last ~90 days; use `tokens["refreshToken"]` to renew without another code.
