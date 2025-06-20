#!/usr/bin/python3

# Copyright (C) 2022 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation; either version 2.1 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; If not, see <http://www.gnu.org/licenses/>.

import os
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

WEBUI_TEST_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.dirname(WEBUI_TEST_DIR)
BOTS_DIR = f'{ROOT_DIR}/bots'

# pylint: disable=environment-modify
sys.path.append(BOTS_DIR)

# pylint: disable=import-error
from machine.machine_core import timeout
from machine.testvm import (
    Machine,  # nopep8
    VirtMachine,  # nopep8
)

# This env variable must be always set for anaconda webui tests.
# In the anaconda environment /run/nologin always exists however cockpit test
# suite expects it to not exist
os.environ["TEST_ALLOW_NOLOGIN"] = "true"


class VirtInstallMachine(VirtMachine):
    http_payload_server = None

    def _execute(self, cmd):
        return subprocess.check_call(cmd, stderr=subprocess.STDOUT, shell=True)

    def _get_free_port(self, start_port=8000):
        port = start_port
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if sock.connect_ex(('127.0.0.1', port)) != 0:
                    return port
            port = port + 1

    def _wait_http_server_running(self, port):
        WAIT_HTTP_RUNNING = """
        until curl --insecure --silent --max-time 3 http://localhost:%s >/dev/null; do
            sleep 0.5;
        done;
        """ % (port)
        with timeout.Timeout(seconds=50, error_message="Timeout while waiting for http server to start"):
            self._execute(WAIT_HTTP_RUNNING)

    def _serve_updates_img(self):
        http_updates_img_port = self._get_free_port()
        self.http_updates_img_server = subprocess.Popen(["python3", "-m", "http.server", "-d", ROOT_DIR, str(http_updates_img_port)])
        self._wait_http_server_running(http_updates_img_port)

        return http_updates_img_port

    def _serve_payload(self):
        payload_cached_path = os.path.realpath(self.payload_path)
        payload_cached_dir = os.path.dirname(payload_cached_path)
        payload_cached_name = os.path.basename(payload_cached_path)

        http_payload_port = self._get_free_port()
        self.http_payload_server = subprocess.Popen(["python3", "-m", "http.server", "-d", payload_cached_dir, str(http_payload_port)])
        self._wait_http_server_running(http_payload_port)

        return payload_cached_name, http_payload_port

    def _write_interactive_defaults_ks(self, updates_image, updates_image_edited):
        payload_cached_name, http_payload_port = self._serve_payload()
        content = f'liveimg --url="http://10.0.2.2:{http_payload_port}/{payload_cached_name}"'
        defaults_path = "usr/share/anaconda/"
        print("Adding interactive defaults to updates.img")
        with TemporaryDirectory() as tmp_dir:
            os.makedirs(f"{tmp_dir}/{defaults_path}")
            # unpack initrd to the temporary directory
            os.system(f"cd {tmp_dir} && gzip -dc {updates_image} | cpio -idu")
            # add new interactive-defaults.ks (have to be available at start of the installer)
            with open(f"{tmp_dir}/{defaults_path}/interactive-defaults.ks", "wt", encoding="utf-8") as f:
                f.write(content)
            # pack the updates.img again and replace the original one
            os.system(f"cd {tmp_dir} && find . | cpio -c -o | gzip -9cv > {updates_image_edited}")

    def start(self):
        self.is_efi = os.environ.get("TEST_FIRMWARE", "bios") == "efi"
        self.os = os.environ.get("TEST_OS", "fedora-rawhide-boot").split("-boot")[0]

        self.payload_path = os.path.join(BOTS_DIR, f"./images/{self.os}-anaconda-payload")
        if not os.path.exists(self.payload_path):
            raise FileNotFoundError(f"Missing payload file {self.payload_path}; use 'make payload'.")

        update_img_global_file = os.path.join(ROOT_DIR, f"updates-{self.os}.img")
        update_img_file = os.path.join(ROOT_DIR, f"{self.label}-updates.img")
        if not os.path.exists(update_img_global_file):
            raise FileNotFoundError("Missing updates.img file")

        if not self.is_live():
            # Configure the payload in interactive-defaults.ks
            self._write_interactive_defaults_ks(update_img_global_file, update_img_file)

        self.http_updates_img_port = self._serve_updates_img()

        # If custom compose if specified for fetching the image then use that
        # else get the image from the bots directory
        if compose := os.environ.get("TEST_COMPOSE"):
            iso_path = f"{os.getcwd()}/test/images/{compose}.iso"
        else:
            iso_path = f"{os.getcwd()}/bots/images/{self.image}"
        extra_args = ""
        if self.is_live():
            # Live install ISO has different directory structure inside
            # that doesn't follow the standard distribution tree directory structure.
            location = f"{iso_path},kernel=images/pxeboot/vmlinuz,initrd=images/pxeboot/initrd.img"

            # Live install ISO will not start automatically without providing correct
            # kernel arguments to load the LiveOS/squashfs.img file as that's where everything is stored.
            volume_id = self.get_volume_id(iso_path)
            extra_args = f"root=live:CDLABEL={volume_id} rd.live.image quiet rhgb"
        else:
            location = f"{iso_path}"

        boot_arg = "--boot uefi " if self.is_efi else ""
        try:
            self._execute(
                "virt-install "
                "--wait "
                "--connect qemu:///session "
                "--quiet "
                f"{boot_arg} "
                f"--name {self.label} "
                f"--os-variant=detect=on "
                "--memory 4096 "
                "--noautoconsole "
                f"--graphics vnc,listen={self.ssh_address} "
                "--extra-args "
                f"'inst.sshd inst.webui.remote inst.updates=http://10.0.2.2:{self.http_updates_img_port}/{self.label}-updates.img' "
                "--network none "
                f"--qemu-commandline="
                "'-netdev user,id=hostnet0,"
                f"hostfwd=tcp:{self.ssh_address}:{self.ssh_port}-:22,"
                f"hostfwd=tcp:{self.web_address}:{self.web_port}-:80 "
                "-device virtio-net-pci,netdev=hostnet0,id=net0,addr=0x16' "
                f"--extra-args '{extra_args}' "
                f"--disk=none "
                f"--location {location} &"
            )

            # Live install ISO does not have sshd service enabled by default
            # so we can't run any Machine.* methods on it.
            if not self.is_live():
                Machine.wait_boot(self, timeout_sec=300)

                for _ in range(30):
                    try:
                        Machine.execute(self, "journalctl -t anaconda | grep 'anaconda: ui.webui: cockpit web view has been started'")
                        break
                    except subprocess.CalledProcessError:
                        time.sleep(10)
                else:
                    raise AssertionError("Webui initialization did not finish")

                # Symlink /usr/share/cockpit to /usr/local/share/cockpit so that rsync works without killing cockpit-bridge
                Machine.execute(self, "mkdir -p /usr/local/share/cockpit/anaconda-webui && mount --bind /usr/share/cockpit /usr/local/share/cockpit")
        except Exception as e:
            self.kill()
            raise e

    def kill(self):
        self._execute(f"virsh -q -c qemu:///session destroy {self.label} || true")
        self._execute(
            f"virsh -q -c qemu:///session undefine --nvram "  # tell undefine to also delete the EFI NVRAM device
            f"--remove-all-storage {self.label} || true"
        )
        if self.http_updates_img_server:
            self.http_updates_img_server.kill()
        if self.http_payload_server:
            self.http_payload_server.kill()

    # pylint: disable=arguments-differ  # this fails locally if you have bots checked out
    def wait_poweroff(self):
        for _ in range(10):
            try:
                self._execute(f"virsh -q -c qemu:///session domstate {self.label} | grep 'shut off'")
                Machine.disconnect(self)
                break
            except subprocess.CalledProcessError:
                time.sleep(2)
        else:
            raise AssertionError("Test VM did not shut off")

    def is_live(self):
        return "live" in self.image

    def get_volume_id(self, iso_path):
        return subprocess.check_output(fr"isoinfo -d -i {iso_path} |  grep -oP 'Volume id: \K.*'", shell=True).decode(sys.stdout.encoding).strip()
