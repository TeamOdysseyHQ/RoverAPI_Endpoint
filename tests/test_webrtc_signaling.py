import unittest

from app.api.webrtc_signaling import defer_mdns_end_of_candidates


class SignalingTests(unittest.TestCase):
    def offer(self, host):
        return f"v=0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\na=candidate:1 1 udp 100 {host} 45678 typ host\r\na=end-of-candidates\r\n"

    def test_mdns_only_defers_end_without_rewriting_addresses(self):
        original = self.offer("browser.local")
        self.assertEqual(defer_mdns_end_of_candidates(original), original.replace("a=end-of-candidates\r\n", ""))

    def test_numeric_candidates_unchanged(self):
        for host in ("192.168.1.54", "2001:db8::1"):
            original = self.offer(host)
            self.assertEqual(defer_mdns_end_of_candidates(original), original)

    def test_mixed_candidates_keep_end(self):
        original = self.offer("browser.local").replace("a=end-of-candidates", "a=candidate:2 1 udp 100 192.168.1.54 45678 typ srflx\r\na=end-of-candidates")
        self.assertEqual(defer_mdns_end_of_candidates(original), original)

    def test_media_sections_are_independent(self):
        first, second = self.offer("browser.local"), self.offer("192.168.1.54").split("\r\n", 1)[1]
        self.assertEqual(defer_mdns_end_of_candidates(first + second), first.replace("a=end-of-candidates\r\n", "") + second)

    def test_empty_or_malformed_candidates_are_unchanged(self):
        for original in ("v=0\r\na=end-of-candidates\r\n", "m=video\na=candidate:invalid\na=end-of-candidates\n"):
            self.assertEqual(defer_mdns_end_of_candidates(original), original)

    def test_lf_and_missing_final_newline_preserved(self):
        original = self.offer("BROWSER.LOCAL").replace("\r\n", "\n").rstrip()
        self.assertEqual(defer_mdns_end_of_candidates(original), original.replace("a=end-of-candidates", ""))


if __name__ == "__main__":
    unittest.main()
