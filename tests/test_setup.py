from __future__ import annotations

import io
import json
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from laneorchestrator.config import load_config
from laneorchestrator.doctor import run_status
from laneorchestrator.profiles import PROFILE_NAMES, ProfileConflict, apply_profiles
from laneorchestrator.setup import (
    INTERACTIVE_COMMAND,
    build_preview,
    render_preview,
    run_interactive,
)
import laneorchestrator.setup as setup_module
from laneorchestrator.voltagent import (
    PACK_AGENT_COUNT,
    PackError,
    apply_install as apply_voltagent_install,
    pack_status,
    render_pack,
)

if os.name == "posix":
    import pty


ROOT = Path(__file__).resolve().parents[1]


class _TTY(io.StringIO):
    def isatty(self) -> bool:
        return True


class _InterruptingTTY(_TTY):
    def readline(self, *args: object, **kwargs: object) -> str:
        raise KeyboardInterrupt


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(prefix="lane orchestrator setup ")
        self.home = Path(self.temporary_directory.name).resolve()
        self.state = self.home / "laneorchestrator"
        self.agents = self.home / "agents"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_setup(self, response: str = "yes\n") -> tuple[object, _TTY]:
        output = _TTY()
        return (
            run_interactive(ROOT, self.state, self.agents, _TTY(response), output),
            output,
        )

    def test_combined_preview_binds_two_exact_plans_without_rendering_secrets(self) -> None:
        preview = build_preview(self.state, self.agents, now=1_000)
        rendered = render_preview(preview, self.agents)

        self.assertEqual(preview.total_changes, 4 + PACK_AGENT_COUNT)
        self.assertEqual(len(preview.fingerprint), 64)
        self.assertIn("Control profiles (4)", rendered)
        self.assertIn("Bundled specialists: 172", rendered)
        self.assertNotIn(preview.profile_token, rendered)
        self.assertNotIn(preview.specialist_token, rendered)
        self.assertNotIn(preview.profile_approval_digest, rendered)
        self.assertNotIn(preview.specialist_approval_digest, rendered)

        with self.assertRaises(ProfileConflict):
            apply_profiles(
                "install",
                preview.profile_token,
                self.agents,
                self.state,
                approval="approve:" + preview.specialist_approval_digest,
                now=1_000,
            )
        self.assertFalse(any((self.agents / name).exists() for name in PROFILE_NAMES))

    def test_confirmation_accepts_only_y_or_yes_and_cancellation_is_safe(self) -> None:
        for response in ("\n", "n\n", "Yess\n", " true\n"):
            with self.subTest(response=response), tempfile.TemporaryDirectory(prefix="lane setup cancel ") as temporary:
                home = Path(temporary).resolve()
                result = run_interactive(ROOT, home / "laneorchestrator", home / "agents", _TTY(response), _TTY())
                self.assertTrue(result.ok)
                self.assertTrue(result.data["cancelled"])
                self.assertFalse(any((home / "agents" / name).exists() for name in PROFILE_NAMES))

        result, _output = self.run_setup("YES\n")
        self.assertTrue(result.ok)
        self.assertTrue(result.data["applied"])

    def test_interrupt_cancels_without_installing(self) -> None:
        result = run_interactive(ROOT, self.state, self.agents, _InterruptingTTY(), _TTY())
        self.assertTrue(result.ok)
        self.assertTrue(result.data["cancelled"])
        self.assertFalse(any((self.agents / name).exists() for name in PROFILE_NAMES))

    def test_non_tty_and_json_mode_are_non_mutating(self) -> None:
        result = run_interactive(ROOT, self.state, self.agents, io.StringIO("yes\n"), _TTY())
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "SETUP_INTERACTIVE_REQUIRED")
        self.assertFalse(self.home.exists() and any(self.home.iterdir()))

        redirected = run_interactive(ROOT, self.state, self.agents, _TTY("yes\n"), io.StringIO())
        self.assertFalse(redirected.ok)
        self.assertEqual(redirected.errors[0]["code"], "SETUP_INTERACTIVE_REQUIRED")
        self.assertFalse(self.home.exists() and any(self.home.iterdir()))

        environment = {**os.environ, "CODEX_HOME": os.fspath(self.home), "PATH": ""}
        piped = subprocess.run(
            [sys.executable, "-m", "laneorchestrator", "setup"],
            cwd=ROOT,
            text=True,
            input="yes\n",
            capture_output=True,
            env=environment,
        )
        self.assertEqual(piped.returncode, 1, piped.stderr)
        self.assertIn("SETUP_INTERACTIVE_REQUIRED", piped.stdout)
        self.assertFalse(self.home.exists() and any(self.home.iterdir()))

        json_result = subprocess.run(
            [sys.executable, "-m", "laneorchestrator", "setup", "--json"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env=environment,
        )
        self.assertEqual(json_result.returncode, 1, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["errors"][0]["code"], "SETUP_INTERACTIVE_REQUIRED")
        self.assertEqual(payload["data"]["interactive_command"], INTERACTIVE_COMMAND)
        self.assertFalse(self.home.exists() and any(self.home.iterdir()))
        self.assertNotIn("approval_digest", json_result.stdout)
        self.assertNotIn("token", json_result.stdout)

    def test_fresh_install_verifies_all_profiles_and_idempotent_rerun_does_not_prompt(self) -> None:
        result, output = self.run_setup()
        self.assertTrue(result.ok)
        self.assertTrue(result.data["applied"])
        self.assertEqual(result.data["control_changes"], 4)
        self.assertEqual(result.data["specialist_changes"], PACK_AGENT_COUNT)
        self.assertEqual(len(list(self.agents.glob("*.toml"))), 4 + PACK_AGENT_COUNT)
        self.assertEqual(pack_status(self.agents).data["installed"], PACK_AGENT_COUNT)
        self.assertEqual(set(run_status(self.state, self.agents).data["managed_profile_state"].values()), {"managed"})
        self.assertNotIn("approve:", output.getvalue())
        self.assertNotIn("approval_digest", output.getvalue())
        self.assertNotIn("token", output.getvalue().casefold())

        rerun_output = _TTY()
        rerun = run_interactive(ROOT, self.state, self.agents, _InterruptingTTY(), rerun_output)
        self.assertTrue(rerun.ok)
        self.assertTrue(rerun.data["already_configured"])
        self.assertFalse(rerun.data["applied"])
        self.assertEqual(rerun_output.getvalue(), "")

    def test_collision_partial_drift_and_symlink_states_are_refused_before_control_apply(self) -> None:
        cases = ("collision", "partial", "drift", "symlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix="lane setup refused ") as temporary:
                home = Path(temporary).resolve()
                agents = home / "agents"
                agents.mkdir()
                if case == "collision":
                    (agents / PROFILE_NAMES[0]).write_text("unmanaged\n", encoding="utf-8")
                elif case == "partial":
                    name, content = next(iter(render_pack().items()))
                    (agents / name).write_bytes(content)
                elif case == "drift":
                    for name, content in render_pack().items():
                        (agents / name).write_bytes(content)
                    (agents / next(iter(render_pack()))).write_text("drift\n", encoding="utf-8")
                else:
                    linked = home / "linked-agents"
                    linked.mkdir()
                    agents.rmdir()
                    agents.symlink_to(linked, target_is_directory=True)

                result = run_interactive(ROOT, home / "laneorchestrator", agents, _TTY("yes\n"), _TTY())
                self.assertFalse(result.ok)
                self.assertEqual(result.errors[0]["code"], "SETUP_REFUSED")
                expected_existing_controls = 1 if case == "collision" else 0
                self.assertEqual(
                    sum((agents / name).exists() for name in PROFILE_NAMES),
                    expected_existing_controls,
                )

    def test_core_first_partial_failure_is_resumable(self) -> None:
        with mock.patch.object(setup_module, "apply_voltagent_install", side_effect=PackError("injected failure")):
            partial, _output = self.run_setup()
        self.assertFalse(partial.ok)
        self.assertEqual(partial.errors[0]["code"], "SETUP_PARTIAL")
        self.assertTrue(partial.data["control_profiles_applied"])
        self.assertTrue(all((self.agents / name).exists() for name in PROFILE_NAMES))
        self.assertEqual(pack_status(self.agents).data["missing"], PACK_AGENT_COUNT)

        recovered, _output = self.run_setup()
        self.assertTrue(recovered.ok)
        self.assertEqual(recovered.data["control_changes"], 0)
        self.assertEqual(recovered.data["specialist_changes"], PACK_AGENT_COUNT)

    def test_core_failure_never_attempts_specialists(self) -> None:
        with mock.patch.object(
            setup_module,
            "apply_profiles",
            side_effect=ProfileConflict("injected core failure"),
        ), mock.patch.object(setup_module, "apply_voltagent_install") as specialist_apply:
            result, _output = self.run_setup()
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "SETUP_CORE_FAILED")
        specialist_apply.assert_not_called()
        self.assertFalse(any((self.agents / name).exists() for name in PROFILE_NAMES))

    def test_exact_plans_refuse_race_and_expiry(self) -> None:
        race = build_preview(self.state, self.agents, now=1_000)
        (self.agents / PROFILE_NAMES[0]).write_text("race\n", encoding="utf-8")
        with self.assertRaises(ProfileConflict):
            apply_profiles(
                "install",
                race.profile_token,
                self.agents,
                self.state,
                approval="approve:" + race.profile_approval_digest,
                now=1_000,
            )

        with tempfile.TemporaryDirectory(prefix="lane setup expiry ") as temporary:
            home = Path(temporary).resolve()
            expired = build_preview(home / "laneorchestrator", home / "agents", now=1_000)
            with self.assertRaises(ProfileConflict):
                apply_profiles(
                    "install",
                    expired.profile_token,
                    home / "agents",
                    home / "laneorchestrator",
                    approval="approve:" + expired.profile_approval_digest,
                    now=1_601,
                )
            with self.assertRaises(PackError):
                apply_voltagent_install(
                    expired.specialist_token,
                    home / "agents",
                    home / "laneorchestrator",
                    approval="approve:" + expired.specialist_approval_digest,
                    now=1_601,
                )

    def test_native_windows_setup_is_refused_with_wsl_guidance(self) -> None:
        with mock.patch.object(setup_module.os, "name", "nt"):
            result = run_interactive(ROOT, self.state, self.agents, _TTY("yes\n"), _TTY())
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["code"], "SETUP_UNSUPPORTED_PLATFORM")
        self.assertIn("WSL", result.errors[0]["message"])

    @unittest.skipUnless(os.name == "posix", "requires a POSIX pseudo-terminal")
    def test_real_pty_install_accepts_one_confirmation(self) -> None:
        master, slave = pty.openpty()
        environment = {**os.environ, "CODEX_HOME": os.fspath(self.home), "PATH": ""}
        process = subprocess.Popen(
            [sys.executable, "-m", "laneorchestrator", "setup"],
            cwd=ROOT,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=environment,
            close_fds=True,
        )
        os.close(slave)
        output = b""
        deadline = time.monotonic() + 20
        try:
            while b"Install these 176 profiles? [y/N]" not in output and time.monotonic() < deadline:
                ready, _write, _error = select.select((master,), (), (), 0.2)
                if ready:
                    output += os.read(master, 8192)
            self.assertIn(b"Install these 176 profiles? [y/N]", output)
            os.write(master, b"yes\n")
            while process.poll() is None and time.monotonic() < deadline:
                ready, _write, _error = select.select((master,), (), (), 0.2)
                if ready:
                    try:
                        output += os.read(master, 8192)
                    except OSError:
                        break
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            os.close(master)
            if process.poll() is None:
                process.kill()
                process.wait()
        decoded = output.decode("utf-8", "replace")
        self.assertIn("setup complete", decoded.casefold())
        self.assertNotIn("approval_digest", decoded)
        self.assertNotIn("approve:", decoded)
        self.assertEqual(len(list(self.agents.glob("*.toml"))), 4 + PACK_AGENT_COUNT)


if __name__ == "__main__":
    unittest.main()
