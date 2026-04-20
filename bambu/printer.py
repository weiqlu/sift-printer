import json
import ssl
import time
from collections.abc import Callable

import requests
from paho.mqtt import client as mqtt


class BambuPrinter:
    """Client for Bambu Lab printers over Bambu's cloud MQTT broker.

    Fetches the user ID and printer serial from Bambu's HTTP API, connects
    to the MQTT broker, streams state updates from the printer, and sends
    control commands to it.

    For the login flow that produces an access token, see bambu.auth.

    Typical usage:

        from bambu import BambuPrinter, login_with_code, send_verification_code

        send_verification_code("you@example.com")
        tokens = login_with_code("you@example.com", "123456")

        printer = BambuPrinter(tokens["accessToken"])
        printer.on_report(lambda r: print(r))
        printer.connect()
        printer.set_light(False)
    """

    BASE = "https://api.bambulab.com"
    MQTT_HOST = "us.mqtt.bambulab.com"
    MQTT_PORT = 8883

    def __init__(self, access_token: str, serial: str | None = None):
        """Build an unconnected client.

        Args:
            access_token: Bambu cloud access token (from login_with_code).
            serial: Optional printer serial. If omitted, the first printer bound
                to the account is used, fetched lazily on first access.
        """
        self.access_token = access_token
        self._serial = serial
        self._user_id: str | None = None
        self._mqtt: mqtt.Client | None = None
        self._on_report: Callable[[dict], None] | None = None

    def _http_get(self, path: str) -> dict:
        """Authenticated GET against Bambu's HTTP API. Internal helper."""
        r = requests.get(
            url=f"{self.BASE}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if not r.ok:
            raise RuntimeError(f"GET {path} failed: {r.status_code} {r.text}")
        return r.json()

    @property
    def user_id(self) -> str:
        """Numeric Bambu user ID. Used to form the MQTT username u_<uid>.

        Fetched lazily from the profile endpoint on first access and cached.
        """
        if self._user_id is None:
            self._user_id = str(self._http_get("/v1/user-service/my/profile")["uid"])
        return self._user_id

    @property
    def serial(self) -> str:
        """Printer serial number used in MQTT topics (device/<serial>/...).

        Returns the value passed to __init__ if provided, otherwise fetches the
        bound devices list and uses the first printer.

        Raises:
            LookupError: If no printers are bound to the account.
        """
        if self._serial is None:
            devices = self._http_get("/v1/iot-service/api/user/bind")["devices"]
            if not devices:
                raise LookupError("No printers bound to this account")
            self._serial = devices[0]["dev_id"]
        return self._serial

    def get_devices(self) -> list[dict]:
        """Return all printers bound to the account.

        Each device dict contains fields like dev_id (serial), name, online
        status, and firmware info.
        """
        return self._http_get("/v1/iot-service/api/user/bind")["devices"]

    def on_report(self, callback: Callable[[dict], None]) -> None:
        """Register a function to run on every message from the printer.

        Callbacks run on the background network thread, so keep them fast
        and make any shared state thread-safe. Replaces any prior callback.
        """
        self._on_report = callback

    def connect(self, timeout: float = 10.0) -> None:
        """Open the MQTT connection and start listening for reports.

        Runs the MQTT network loop on a background thread, so this call
        returns once the connection is established. Every (re)connect also
        asks the printer for a full state snapshot, so your report callback
        receives the current state right away instead of waiting for the
        next field to change.

        Args:
            timeout: Seconds to wait for the connection to complete before
                giving up.

        Raises:
            TimeoutError: If the broker does not confirm the connection in
                time (usually bad credentials, firewall, or broker down).
        """
        user_id = self.user_id
        serial = self.serial

        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"bambu-{user_id}",
        )
        client.username_pw_set(f"u_{user_id}", self.access_token)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        def on_connect(c, userdata, flags, reason_code, properties):
            c.subscribe(f"device/{serial}/report")
            # Prime a full-state snapshot on every (re)connect.
            c.publish(
                f"device/{serial}/request",
                json.dumps({"pushing": {"command": "pushall"}}),
            )

        def on_message(c, userdata, msg):
            if self._on_report is not None:
                self._on_report(json.loads(msg.payload))

        client.on_connect = on_connect
        client.on_message = on_message

        client.connect(self.MQTT_HOST, self.MQTT_PORT, keepalive=60)
        client.loop_start()

        deadline = time.time() + timeout
        while not client.is_connected():
            if time.time() > deadline:
                client.loop_stop()
                raise TimeoutError("MQTT connect timed out")
            time.sleep(0.05)

        self._mqtt = client

    def disconnect(self) -> None:
        """Stop the background loop and close the MQTT connection.

        Safe to call multiple times; no-op if not connected.
        """
        if self._mqtt is not None:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
            self._mqtt = None

    def __enter__(self) -> "BambuPrinter":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

    def _publish(self, payload: dict) -> None:
        """Publish a JSON command to the printer's request topic. Internal helper."""
        if self._mqtt is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self._mqtt.publish(f"device/{self.serial}/request", json.dumps(payload))

    def request_full_state(self) -> None:
        """Ask the printer to publish a full-state snapshot immediately."""
        self._publish({"pushing": {"command": "pushall"}})

    def set_light(self, on: bool) -> None:
        """Turn the chamber LED on or off."""
        self._publish(
            {
                "system": {
                    "sequence_id": "0",
                    "command": "ledctrl",
                    "led_node": "chamber_light",
                    "led_mode": "on" if on else "off",
                    "led_on_time": 500,
                    "led_off_time": 500,
                    "led_loop_times": 0,
                    "led_interval_time": 0,
                }
            }
        )

    def pause(self) -> None:
        """Pause the current print job."""
        self._publish({"print": {"command": "pause", "sequence_id": "0"}})

    def resume(self) -> None:
        """Resume a paused print job."""
        self._publish({"print": {"command": "resume", "sequence_id": "0"}})

    def stop(self) -> None:
        """Cancel the current print job."""
        self._publish({"print": {"command": "stop", "sequence_id": "0"}})
