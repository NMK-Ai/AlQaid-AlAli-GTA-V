import json
import socket
import struct
import unittest

from protocol import VERSION, COMMAND, TELEMETRY, decode_telemetry, receive_json

class TransportTests(unittest.TestCase):
    def test_native_layout_and_corrupt_telemetry(self):
        self.assertEqual(TELEMETRY.size, 132)
        self.assertEqual(COMMAND.size, 44)
        values = [0x5447504f, VERSION, 2, 300, 4, 5, 6, 7, *([0.]*22), 0]
        self.assertEqual(decode_telemetry(TELEMETRY.pack(*values))['vehicle'], 5)
        values[1] = VERSION-1
        with self.assertRaises(ValueError):
            decode_telemetry(TELEMETRY.pack(*values))
        values[1] = VERSION
        with self.assertRaises(ValueError):
            decode_telemetry(b'bad')
        values[0] = 0
        with self.assertRaises(ValueError):
            decode_telemetry(TELEMETRY.pack(*values))
        values[0], values[-2] = 0x5447504f, float('nan')
        with self.assertRaises(ValueError):
            decode_telemetry(TELEMETRY.pack(*values))

    def test_oversized_header_and_truncated_connection(self):
        for content, expected in ((struct.pack('<I', 8193), ValueError),
                                  (struct.pack('<I', 10)+b'{}', ConnectionError)):
            a, b = socket.socketpair()
            with a, b:
                a.sendall(content)
                a.shutdown(socket.SHUT_WR)
                with self.assertRaises(expected):
                    receive_json(b)

    def test_back_to_back_messages_stay_separate(self):
        a, b = socket.socketpair()
        with a, b:
            for value in ({'frame': 12}, {'frame': 13}):
                data = json.dumps(value).encode()
                a.sendall(struct.pack('<I', len(data))+data)
            self.assertEqual(receive_json(b), {'frame': 12})
            self.assertEqual(receive_json(b), {'frame': 13})

if __name__ == '__main__':
    unittest.main()
