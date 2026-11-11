"""Membuka Nero tanpa terminal: ikon Desktop & Start Menu, buka otomatis, satu Nero saja."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest import mock

from tests.util import ROOT  # noqa: F401  (menambahkan folder aplikasi ke sys.path)

import desktop  # noqa: E402


class SatuNero(unittest.TestCase):
    def test_belum_berjalan(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()  # port kosong: tidak ada Nero di sana
        self.assertFalse(desktop.nero_running(f"http://127.0.0.1:{port}"))


def read_lnk(path):
    """Target & argumen sebuah shortcut .lnk (dibaca lewat PowerShell)."""
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LNK);"
          "Write-Output $s.TargetPath; Write-Output $s.Arguments; Write-Output $s.WorkingDirectory")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                         env={**os.environ, "LNK": path}, capture_output=True, text=True, check=True).stdout
    return out.splitlines()


@unittest.skipUnless(desktop.SUPPORTED, "khusus Windows")
class Ikon(unittest.TestCase):
    """Desktop, Start Menu, Startup, dan data/ sementara: ikon milik pengguna tidak tersentuh."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nero test ")  # spasi di nama folder harus aman
        self.dirs = {desktop._DESKTOP: os.path.join(self.tmp, "Desktop"),
                     desktop._PROGRAMS: os.path.join(self.tmp, "Programs"),
                     desktop._STARTUP: os.path.join(self.tmp, "Startup")}
        data = os.path.join(self.tmp, "data")
        os.makedirs(data)
        self.patches = [
            mock.patch.object(desktop, "_folder", lambda csidl: self.dirs[csidl]),
            mock.patch.object(desktop, "ICON_PATH", os.path.join(data, "nero.ico")),
            mock.patch.object(desktop, "STATE_PATH", os.path.join(data, "desktop.json")),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lnk(self, csidl):
        return os.path.join(self.dirs[csidl], "Nero.lnk")

    def test_buat_ikon_dan_buka_otomatis(self):
        self.assertEqual(desktop.status(), {"shortcut": False, "autostart": False})
        desktop.create_shortcuts()
        self.assertTrue(os.path.isfile(self.lnk(desktop._PROGRAMS)))
        self.assertGreater(os.path.getsize(desktop.ICON_PATH), 0)
        target, args, workdir = read_lnk(self.lnk(desktop._DESKTOP))
        self.assertTrue(target.lower().endswith("pythonw.exe"))
        self.assertEqual(args, f'"{desktop.APP_PY}"')
        self.assertEqual(os.path.normcase(workdir), os.path.normcase(desktop.APP_DIR))

        desktop.set_autostart(True)
        self.assertEqual(desktop.status(), {"shortcut": True, "autostart": True})
        self.assertEqual(read_lnk(self.lnk(desktop._STARTUP))[1], f'"{desktop.APP_PY}" --background')
        desktop.set_autostart(False)
        desktop.set_autostart(False)  # sudah mati: tidak galat
        self.assertEqual(desktop.status(), {"shortcut": True, "autostart": False})

    def test_folder_dipindah(self):
        with open(desktop.STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"app_dir": r"D:\lama\ClipMaker"}, f)
        os.makedirs(self.dirs[desktop._DESKTOP])
        open(self.lnk(desktop._DESKTOP), "w").close()
        with mock.patch.object(desktop, "create_shortcuts") as shortcuts, \
                mock.patch.object(desktop, "set_autostart") as autostart, mock.patch("builtins.print"):
            desktop.refresh_if_moved()
        shortcuts.assert_called_once()
        autostart.assert_not_called()  # buka otomatis tidak pernah dinyalakan
        with open(desktop.STATE_PATH, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["app_dir"], desktop.APP_DIR)

        with mock.patch.object(desktop, "create_shortcuts") as shortcuts:
            desktop.refresh_if_moved()  # sudah di lokasi yang benar
        shortcuts.assert_not_called()

    def test_ikon_belum_pernah_dibuat(self):
        with mock.patch.object(desktop, "create_shortcuts") as shortcuts:
            desktop.refresh_if_moved()
        shortcuts.assert_not_called()
        self.assertFalse(os.path.exists(desktop.STATE_PATH))


if __name__ == "__main__":
    unittest.main()
