#!/usr/bin/env python

"""
This is a utility for controller MagicHome RGBWWCW Led Lights. Commands were reverse engineered from a RGBWWCW
WIFI controller. Seems to work fine, but... I have only tested this on RGB, so report any bugs in github issues.

I've not ported all the MagicHome app functionality as I don't see any need, given that this is to be used with
home-assistant

##### Functionality available
* Discovery on LAN
* Turning the LED Strips on and off.
* State information
* Setting warm white
* Setting cold white
* Setting RGB Values

##### Not implemented
* Administration and setup of WIFI Controllers. To do this, download the app!
* Remote access administration
* Music related pulsing - Use HUE Emulation in Home Assistant
* Picture / Image based colour changes - See above

##### TODO
* Setting Preset Program
* Setting Custom Program
* Setting Program Speed
* Reading timers
* Setting timers
"""

import socket
import threading
import colorsys
import time


class MagicHomeLEDController:
    def __init__(self, ip, port=5577):
        self._lock = threading.Lock()
        self._ip = ip
        self._port = port
        self._is_on = False
        self._rgb = []
        self._warm_white = 0
        self._cold_white = 0
        self._mode = None
        self._brightness = 0

    @staticmethod
    def scan(timeout=10):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('', 48899))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        msg = "HF-A11ASSISTHREAD".encode("ascii")
        timeout = time.time() + timeout
        found = []
        sock.sendto(msg, ('<broadcast>', 48899))
        while True:
            if time.time() > timeout:
                break
            sock.settimeout(1)
            try:
                data, addr = sock.recvfrom(64)
            except:
                data = None
                if time.time() > timeout:
                    break
            if data is None:
                continue
            if data == msg:
                continue

            data = data.decode("ascii")
            ss = data.split(",")
            if len(ss) < 3:
                continue
            device = dict()
            device['ip'] = ss[0]
            device['mac'] = ss[1]
            device['type'] = ss[2]
            found.append(device)
        return found

    @property
    def is_on(self):
        return self._is_on

    @property
    def mode(self):
        return self._mode

    @property
    def rgb(self):
        return self._rgb

    @property
    def warm_white(self):
        return self._warm_white

    @property
    def cold_white(self):
        return self._cold_white

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self._ip, self._port))
            self.update_state()
        except socket.error:
            pass

    def close(self):
        try:
            self.socket.close()
        except socket.error:
            pass

    def update_state(self):
        try:
            self._send_msg(bytearray([0x81, 0x8A, 0x8B, 0x96]), False)
            state = self._read_msg(15)
            print(state)
        except socket.error:
            self._is_on = False
            pass
        # Reading and updating variables requires a lock
        with self._lock:
            # self._mode = self._get_mode(state)
            if state[2] == 0x23:
                self._is_on = True
            else:
                self._is_on = False
            self._rgb = [state[6], state[7], state[8]]
            self._warm_white = state[9]
            self._cold_white = state[10]
            self._brightness = self._calculate_brightness(self._rgb)

    def set_rgb(self, rgb, ww=0, cw=0, brightness=None):
        # Ensure that the RGB array is of len 3
        if len(rgb) < 3:
            raise Exception("You need to specific at least three values for RGB")
        # Check the RGB Values
        for c in rgb:
            if c > 255 or c < 0:
                raise Exception("RGB Values must be between 0 and 255")
        # Build a message
        msg = bytearray([0x31])
        if cw < 1 and ww < 1:
            if brightness is not None:
                rgb = self._calculate_brightness(rgb, 0, 0, brightness)
            msg.extend(rgb)
            msg.extend([0, 0])
        elif cw > 0:
            msg.extend([0, 0, 0, 0, cw])
        elif ww > 0:
            msg.extend([0, 0, 0, ww, 0])
        msg.extend([0xf0, 0x0f])
        self._send_msg(msg)

    def set_brightness(self, brightness):
        if self._warm_white <= 0 and self._cold_white <= 0:
            self.set_rgb(self._rgb, 0, 0, brightness)
        return

    def set_warm_white(self, warm_white):
        self.set_rgb([0, 0, 0, warm_white, 0])
        return

    def set_cold_white(self, cold_white):
        self.set_cold_white([0, 0, 0, cold_white, 0])
        return

    def turn_on(self):
        self._send_msg(bytearray([0x71, 0x23, 0x0f]))
        return

    def turn_off(self):
        self._send_msg(bytearray([0x71, 0x24, 0x0f]))
        return

    def _get_mode(self, data):
        return "unknown"

    def _calculate_brightness(self, rgb, ww=0, cw=0, level=-1):
        r = rgb[0]
        g = rgb[1]
        b = rgb[2]
        if ww > 0 or cw > 0:
            if level < 0 < cw:
                level = cw
            elif level < 0 < ww:
                level = ww
            hsv = colorsys.rgb_to_hsv(255, 255, 255)
        else:
            hsv = colorsys.rgb_to_hsv(r, g, b)
        if level >= 0:
            return colorsys.hsv_to_rgb(hsv[0], hsv[1], level)
        return colorsys.hsv_to_rgb(hsv[0], hsv[1], hsv[2])

    def _send_msg(self, data, calculate_checksum=True):
        try:
            if calculate_checksum:
                csum = sum(data) & 0xFF
            data.append(csum)
            with self._lock:
                self.socket.send(data)
        except:
            pass

    def _read_msg(self, expected):
        remaining = expected
        bytes = bytearray()
        with self._lock:
            while remaining > 0:
                try:
                    chunk = self.socket.recv(remaining)
                    remaining -= len(chunk)
                    bytes.extend(chunk)
                    return bytes
                except socket.error:
                    pass
