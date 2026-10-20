"""Motor board stand-in (V0): answers the set point frames of the HMI with a status frame."""

import e2sim

SOF, CMD_SET, CMD_STATUS = 0xA5, 0x01, 0x81


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def frame(cmd: int, payload: bytes) -> bytes:
    body = bytes([cmd, len(payload)]) + payload
    return bytes([SOF]) + body + bytes([crc8(body)])


class MotorBoard(e2sim.Model):
    uart = e2sim.Stream()
    no_answer = e2sim.Param(False, "fault: board silent")
    corrupt_crc = e2sim.Param(False, "fault: bad CRC on every status")
    faults = e2sim.Param(0, "fault flags reported (1 overcurrent, 2 blocked)")
    time_constant_s = e2sim.Param(0.3, "speed response")

    def setup(self):
        self.rx = bytearray()
        self.target = 0
        self.rpm = 0.0
        self.frames = 0

    @e2sim.every(ms=10)
    def motor(self):
        target = 0 if self.faults else self.target
        self.rpm += (target - self.rpm) * min(1.0, 0.01 / self.time_constant_s)

    def on_uart(self, data: bytes):
        self.rx += data
        while len(self.rx) >= 4:
            if self.rx[0] != SOF:
                del self.rx[0]
                continue
            n = self.rx[2]
            if len(self.rx) < 4 + n:
                return
            body, crc = bytes(self.rx[1:3 + n]), self.rx[3 + n]
            del self.rx[:4 + n]
            if crc8(body) == crc and body[0] == CMD_SET and n == 3:
                self.frames += 1
                self.target = (body[2] | (body[3] << 8)) if body[4] else 0
                self.answer()

    def answer(self):
        if self.no_answer:
            return
        rpm = round(self.rpm)
        f = frame(CMD_STATUS, bytes([rpm & 0xFF, rpm >> 8, self.faults & 0xFF]))
        if self.corrupt_crc:
            f = f[:-1] + bytes([f[-1] ^ 0xFF])
        self.uart.write(f)
