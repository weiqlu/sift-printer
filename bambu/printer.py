import json
import ssl
import time
from collections.abc import Callable

import requests
from paho.mqtt import client as mqtt


class BambuPrinter:
    BASE = "https://api.bambulab.com"
    MQTT_HOST = "us.mqtt.bambulab.com"
    MQTT_PORT = 8883

    def __init__(self, access_token: str, serial: str | None = None):
        self.access_token = access_token
        self._serial = serial
        self._user_id: str | None = None
        self._mqtt: mqtt.Client | None = None
        self._on_report: Callable[[dict], None] | None = None

    @staticmethod
    def send_verification_code(email: str) -> None:
        r = requests.post(
            url=f"{BambuPrinter.BASE}/v1/user-service/user/sendemail/code",
            json={"email": email, "type": "codeLogin"},
        )
        if not r.ok:
            raise RuntimeError(f"sendemail/code failed: {r.status_code} {r.text}")

    @staticmethod
    def login_with_code(email: str, code: str) -> dict:
        """Returns {accessToken, refreshToken, expiresIn}."""
        r = requests.post(
            url=f"{BambuPrinter.BASE}/v1/user-service/user/login",
            json={"account": email, "code": code},
        )
        if not r.ok:
            raise RuntimeError(f"login failed: {r.status_code} {r.text}")
        return r.json()

    def _http_get(self, path: str) -> dict:
        r = requests.get(
            url=f"{self.BASE}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        if not r.ok:
            raise RuntimeError(f"GET {path} failed: {r.status_code} {r.text}")
        return r.json()

    @property
    def user_id(self) -> str:
        if self._user_id is None:
            self._user_id = str(self._http_get("/v1/user-service/my/profile")["uid"])
        return self._user_id

    @property
    def serial(self) -> str:
        if self._serial is None:
            devices = self._http_get("/v1/iot-service/api/user/bind")["devices"]
            if not devices:
                raise LookupError("No printers bound to this account")
            self._serial = devices[0]["dev_id"]
        return self._serial

    def get_devices(self) -> list[dict]:
        return self._http_get("/v1/iot-service/api/user/bind")["devices"]

    def on_report(self, callback: Callable[[dict], None]) -> None:
        """Register a callback invoked with every parsed report message."""
        self._on_report = callback

    def connect(self, timeout: float = 10.0) -> None:
        """Open the MQTT connection, prime full state, and start the background loop."""
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
        if self._mqtt is not None:
            self._mqtt.loop_stop()
            self._mqtt.disconnect()
            self._mqtt = None
            

    def _publish(self, payload: dict) -> None:
        if self._mqtt is None:
            raise RuntimeError("Not connected — call connect() first")
        self._mqtt.publish(f"device/{self.serial}/request", json.dumps(payload))

    def request_full_state(self) -> None:
        self._publish({"pushing": {"command": "pushall"}})

    def set_light(self, on: bool) -> None:
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
        self._publish({"print": {"command": "pause", "sequence_id": "0"}})

    def resume(self) -> None:
        self._publish({"print": {"command": "resume", "sequence_id": "0"}})

    def stop(self) -> None:
        self._publish({"print": {"command": "stop", "sequence_id": "0"}})
