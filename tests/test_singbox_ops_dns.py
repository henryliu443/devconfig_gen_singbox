import unittest

from singbox_ops.adapters.dns.cloudflare import MANAGED_COMMENT, CloudflareDNS
from tests._ops_support import FakeCloudflare

HOSTS = {
    "anytls": "a1b2.example.com",
    "tuic": "c3d4.example.com",
    "hysteria2": "e5f6.example.com",
}


def adapter(http):
    return CloudflareDNS(token="token", zone_id="zone", http=http)


class CloudflareDNSTests(unittest.TestCase):
    def test_apply_creates_records(self):
        http = FakeCloudflare()
        record_ids = adapter(http).apply(HOSTS, "203.0.113.10")
        self.assertEqual(set(record_ids), set(HOSTS.values()))
        self.assertEqual(len(http.records), 3)
        for record in http.records.values():
            self.assertEqual(record["content"], "203.0.113.10")
            self.assertEqual(record["comment"], MANAGED_COMMENT)

    def test_apply_is_idempotent(self):
        http = FakeCloudflare()
        first = adapter(http).apply(HOSTS, "203.0.113.10")
        second = adapter(http).apply(HOSTS, "203.0.113.10")
        self.assertEqual(first, second)
        self.assertEqual(len(http.records), 3)

    def test_ip_change_recreates_records(self):
        http = FakeCloudflare()
        adapter(http).apply(HOSTS, "203.0.113.10")
        updated = adapter(http).apply(HOSTS, "203.0.113.99")
        self.assertEqual(len(updated), 3)
        self.assertEqual(len(http.records), 3)
        for record in http.records.values():
            self.assertEqual(record["content"], "203.0.113.99")

    def test_unmanaged_records_are_never_touched(self):
        http = FakeCloudflare()
        http.records["mine"] = {
            "id": "mine",
            "name": "keep.example.com",
            "content": "1.2.3.4",
            "comment": "operator",
        }
        adapter(http).apply(HOSTS, "203.0.113.10")
        self.assertIn("mine", http.records)

    def test_destroy_removes_records(self):
        http = FakeCloudflare()
        record_ids = adapter(http).apply(HOSTS, "203.0.113.10")
        adapter(http).destroy(record_ids)
        self.assertEqual(http.records, {})

    def test_dry_run_does_not_touch_api(self):
        http = FakeCloudflare()
        record_ids = adapter(http).apply(HOSTS, "203.0.113.10", dry_run=True)
        self.assertEqual(http.records, {})
        self.assertTrue(all(value.startswith("dry-run:") for value in record_ids.values()))


if __name__ == "__main__":
    unittest.main()
