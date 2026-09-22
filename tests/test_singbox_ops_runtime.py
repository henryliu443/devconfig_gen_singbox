import unittest

from singbox_ops.adapters.runtime.auto_update import AutoUpdateRuntime
from singbox_ops.adapters.runtime.nftables import (
    NftablesFirewall,
    build_nftables_conf,
    detect_ssh_port,
)
from singbox_ops.adapters.runtime.packages import DebianPackagesRuntime
from singbox_ops.adapters.runtime.systemd import SystemdRuntime
from singbox_ops.adapters.runtime.warp_watchdog import (
    WarpWatchdogRuntime,
    build_watchdog_script,
)
from singbox_ops.core.plan import DeployPlan
from tests._ops_support import FakeRunner


def plan_for(tunnel_mode="proxy", protocols=("anytls", "tuic", "hysteria2")):
    return DeployPlan.from_mapping(
        {
            "domain_root": "example.com",
            "tunnel_mode": tunnel_mode,
            "protocols": list(protocols),
        }
    )


class NftablesTests(unittest.TestCase):
    def test_conf_opens_protocol_ports(self):
        conf = build_nftables_conf([23244], [9443, 7443], ssh_port=2222)
        self.assertIn("policy accept", conf)
        self.assertIn("tcp dport { 23244 } accept", conf)
        self.assertIn("udp dport { 7443, 9443 } accept", conf)
        self.assertIn("tcp dport 2222", conf)
        self.assertIn("tcp flags", conf)

    def test_detect_ssh_port_from_config(self):
        runner = FakeRunner(
            existing=["/etc/ssh/sshd_config"],
            files={"/etc/ssh/sshd_config": "Port 2222\n"},
        )
        self.assertEqual(detect_ssh_port(runner), 2222)

    def test_detect_ssh_port_default(self):
        self.assertEqual(detect_ssh_port(FakeRunner()), 22)

    def test_apply_deletes_legacy_table_then_loads(self):
        runner = FakeRunner()
        NftablesFirewall(runner=runner).apply(plan_for(), {})
        runs = [cmd[1] for cmd in runner.commands if cmd[0] == "run"]
        self.assertIn(("nft", "delete", "table", "inet", "singbox_guard"), runs)
        self.assertTrue(any(item[0] == "nft" and item[1] == "-f" for item in runs))
        self.assertTrue(runner.writes)


class SystemdTests(unittest.TestCase):
    def test_apply_writes_unit_and_restarts(self):
        runner = FakeRunner()
        SystemdRuntime(runner=runner).apply(plan_for(), {})
        paths = [path for path, _, _ in runner.writes]
        self.assertIn("/etc/systemd/system/sing-box.service", paths)
        command_names = [cmd[1][0] for cmd in runner.commands if cmd[0] == "run"]
        self.assertIn("sing-box", command_names)
        self.assertIn("systemctl", command_names)

    def test_destroy_disables_and_removes_unit(self):
        runner = FakeRunner()
        SystemdRuntime(runner=runner).destroy(plan_for(), {})
        self.assertIn("/etc/systemd/system/sing-box.service", runner.removed)


class WatchdogTests(unittest.TestCase):
    def test_script_embeds_mode(self):
        script = build_watchdog_script("proxy")
        self.assertIn('WARP_MODE="proxy"', script)
        self.assertIn("check_warp_data_plane", script)

    def test_apply_writes_script_and_cron(self):
        runner = FakeRunner()
        WarpWatchdogRuntime(runner=runner).apply(plan_for("proxy"), {})
        paths = [path for path, _, _ in runner.writes]
        self.assertIn("/root/warp_lazy_watchdog.sh", paths)
        self.assertIn("/etc/cron.d/singbox-warp-watchdog", paths)

    def test_direct_mode_cancels_watchdog_and_kills_warp(self):
        runner = FakeRunner()
        WarpWatchdogRuntime(runner=runner).apply(plan_for("none"), {})
        self.assertEqual(runner.writes, [])
        self.assertIn("/etc/cron.d/singbox-warp-watchdog", runner.removed)
        self.assertIn("/root/warp_lazy_watchdog.sh", runner.removed)
        runs = [cmd[1] for cmd in runner.commands if cmd[0] == "run"]
        self.assertIn(("pkill", "-9", "-x", "warp-svc"), runs)


class AutoUpdateTests(unittest.TestCase):
    def test_apply_writes_script_and_cron(self):
        runner = FakeRunner()
        AutoUpdateRuntime(runner=runner).apply(plan_for("none"), {})
        paths = [path for path, _, _ in runner.writes]
        self.assertIn("/usr/local/bin/singbox_auto_update.py", paths)
        self.assertIn("/etc/cron.d/singbox-auto-update", paths)
        cron = next(text for path, text, _ in runner.writes if path.endswith("singbox-auto-update"))
        self.assertIn("17 4 * * *", cron)
        script = next(text for path, text, _ in runner.writes if path.endswith("singbox_auto_update.py"))
        self.assertIn("SagerNet/sing-box", script)

    def test_destroy_removes_both(self):
        runner = FakeRunner()
        AutoUpdateRuntime(runner=runner).destroy(plan_for("none"), {})
        self.assertIn("/etc/cron.d/singbox-auto-update", runner.removed)
        self.assertIn("/usr/local/bin/singbox_auto_update.py", runner.removed)


class PackagesTests(unittest.TestCase):
    def test_installs_singbox_when_missing(self):
        runner = FakeRunner()

        def which(name):
            if name in ("openssl", "curl"):
                return f"/usr/bin/{name}"
            return None

        DebianPackagesRuntime(runner=runner, which=which).apply(plan_for("none"), {})
        self.assertTrue(any(cmd[0] == "shell" and "sing-box" in cmd[1] for cmd in runner.commands))

    def test_leaves_healthy_server_alone(self):
        runner = FakeRunner()

        def which(name):
            return f"/usr/bin/{name}"

        DebianPackagesRuntime(runner=runner, which=which).apply(plan_for("none"), {})
        self.assertEqual(runner.commands, [])
        self.assertEqual(runner.shell_commands, [])

    def test_dry_run_does_nothing(self):
        runner = FakeRunner()
        DebianPackagesRuntime(runner=runner, which=lambda name: None).apply(
            plan_for("proxy"), {}, dry_run=True
        )
        self.assertEqual(runner.commands, [])


if __name__ == "__main__":
    unittest.main()
