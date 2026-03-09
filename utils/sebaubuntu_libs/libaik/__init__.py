#
# Copyright (C) 2022 Sebastiano Barezzi
#
# SPDX-License-Identifier: Apache-2.0
#
"""AIK wrapper library."""

from pathlib import Path
from platform import system
from sebaubuntu_libs.liblogging import LOGI
from shutil import which, copytree, rmtree
from subprocess import check_output, STDOUT, CalledProcessError, run, DEVNULL
from tempfile import TemporaryDirectory
from typing import List, Optional

AIK_REPO = "https://github.com/SebaUbuntu/AIK-Linux-mirror"
# Local AIK-Linux path bundled with DumprX (avoids cloning at runtime)
_LOCAL_AIK = Path(__file__).resolve().parent.parent.parent / "AIK-Linux"

ALLOWED_OS = [
	"Linux",
	"Darwin",
]

# CPIO newc trailer marker
_CPIO_TRAILER = b'TRAILER!!!'
# Files that identify a recovery ramdisk
_RECOVERY_PROP_NAMES = (b'prop.default', b'default.prop', b'build.prop')


def _split_cpio_archives(data: bytes) -> List[bytes]:
	"""Split concatenated CPIO archives at TRAILER!!! boundaries.

	vendor_boot v4 combined ramdisks contain multiple CPIO archives
	concatenated. Each ends with a TRAILER!!! entry + null padding.
	"""
	archives = []
	offset = 0
	while offset < len(data):
		while offset < len(data) and data[offset:offset + 1] == b'\x00':
			offset += 1
		if offset >= len(data):
			break
		trailer_pos = data.find(_CPIO_TRAILER, offset)
		if trailer_pos == -1:
			# 110 = minimum cpio newc header size (6 magic + 8*13 fields + filename)
			if len(data) - offset > 110:
				archives.append(data[offset:])
			break
		end = trailer_pos + len(_CPIO_TRAILER)
		end = (end + 3) & ~3
		archives.append(data[offset:end])
		offset = end
	return archives

class AIKImageInfo:
	def __init__(
		self,
		base_address: Optional[str],
		board_name: Optional[str],
		cmdline: Optional[str],
		dt: Optional[Path],
		dtb: Optional[Path],
		dtb_offset: Optional[str],
		dtbo: Optional[Path],
		header_version: Optional[str],
		image_type: Optional[str],
		kernel: Optional[Path],
		kernel_offset: Optional[str],
		origsize: Optional[str],
		os_version: Optional[str],
		pagesize: Optional[str],
		ramdisk: Optional[Path],
		ramdisk_compression: Optional[str],
		ramdisk_offset: Optional[str],
		sigtype: Optional[str],
		tags_offset: Optional[str],
	):
		self.kernel = kernel
		self.dt = dt
		self.dtb = dtb
		self.dtbo = dtbo
		self.ramdisk = ramdisk
		self.base_address = base_address
		self.board_name = board_name
		self.cmdline = cmdline
		self.dtb_offset = dtb_offset
		self.header_version = header_version
		self.image_type = image_type
		self.kernel_offset = kernel_offset
		self.origsize = origsize
		self.os_version = os_version
		self.pagesize = pagesize
		self.ramdisk_compression = ramdisk_compression
		self.ramdisk_offset = ramdisk_offset
		self.sigtype = sigtype
		self.tags_offset = tags_offset

	def __str__(self):
		return (
			f"base address: {self.base_address}\n"
			f"board name: {self.board_name}\n"
			f"cmdline: {self.cmdline}\n"
			f"dtb offset: {self.dtb_offset}\n"
			f"header version: {self.header_version}\n"
			f"image type: {self.image_type}\n"
			f"kernel offset: {self.kernel_offset}\n"
			f"original size: {self.origsize}\n"
			f"os version: {self.os_version}\n"
			f"page size: {self.pagesize}\n"
			f"ramdisk compression: {self.ramdisk_compression}\n"
			f"ramdisk offset: {self.ramdisk_offset}\n"
			f"sigtype: {self.sigtype}\n"
			f"tags offset: {self.tags_offset}\n"
		)

class AIKManager:
	"""
	This class is responsible for dealing with AIK tasks
	such as cloning, updating, and extracting recovery images.
	"""

	UNPACKING_FAILED_STRING = "Unpacking failed, try without --nosudo."

	def __init__(self):
		"""Initialize AIKManager class."""
		if system() not in ALLOWED_OS:
			raise NotImplementedError(f"{system()} is not supported")

		# Check whether cpio package is installed
		if which("cpio") is None:
			raise RuntimeError("cpio package is not installed")

		self.tempdir = TemporaryDirectory()
		self.path = Path(self.tempdir.name)

		self.images_path = self.path / "split_img"
		self.ramdisk_path = self.path / "ramdisk"

		# Use local AIK-Linux bundled with DumprX if available
		if _LOCAL_AIK.is_dir() and (_LOCAL_AIK / "unpackimg.sh").is_file():
			LOGI("Using local AIK-Linux...")
			copytree(str(_LOCAL_AIK), str(self.path), dirs_exist_ok=True)
		else:
			LOGI("Cloning AIK...")
			from git import Repo
			Repo.clone_from(AIK_REPO, self.path)

	def unpackimg(self, image: Path, ignore_ramdisk_errors: bool = False):
		"""Extract recovery image."""
		image_prefix = image.name

		try:
			process = self._execute_script("unpackimg.sh", image)
		except CalledProcessError as e:
			returncode = e.returncode
			output = e.output
		else:
			returncode = 0
			output = process

		if returncode != 0:
			if self.UNPACKING_FAILED_STRING in output and ignore_ramdisk_errors:
				try:
					self.ramdisk_path.rmdir()
				except Exception:
					pass
			else:
				raise RuntimeError(f"AIK extraction failed, return code {returncode}")

		# vendor_boot v4: combined ramdisk has concatenated CPIOs.
		# AIK only extracts the first one (base ramdisk with modules).
		# We need the recovery CPIO (the one with prop.default) instead.
		header_version = self._read_recovery_file(image_prefix, "header_version", default="0")
		image_type = self._read_recovery_file(image_prefix, "imgtype")
		if image_type and "VNDR" in image_type and int(header_version or "0") >= 4:
			self._select_recovery_ramdisk(image_prefix)

		return self._get_current_extracted_info(image_prefix)

	def _select_recovery_ramdisk(self, image_prefix: str):
		"""For vendor_boot v4, extract only the recovery CPIO from the combined ramdisk.

		The combined vendor ramdisk contains multiple concatenated CPIO archives:
		  - base ramdisk (kernel modules, fstab) — extracted by AIK
		  - recovery ramdisk (prop.default, recovery.fstab, init.rc) — skipped by AIK

		The recovery content may be split across multiple CPIOs (one with props,
		another with services/fstab). This method identifies all recovery-related
		archives and extracts them into a single ramdisk.
		"""
		# Find compressed ramdisk file from AIK's split_img
		comp_file = None
		for f in self.images_path.iterdir():
			if image_prefix in f.name and "vendor_ramdisk" in f.name and f.stat().st_size > 0:
				comp_file = f
				break
		if not comp_file:
			return

		comp_type = self._read_recovery_file(image_prefix, "vendor_ramdiskcomp") or ""

		# Decompress the full combined ramdisk
		decompressed = self.path / "_full_vendor_ramdisk"
		try:
			with open(decompressed, "wb") as out_f:
				if "lz4" in comp_type:
					run(["lz4", "-dc", "-l", str(comp_file)],
					    stdout=out_f, stderr=DEVNULL, check=True)
				elif "gzip" in comp_type or "gz" in comp_type:
					run(["gzip", "-dc", str(comp_file)],
					    stdout=out_f, stderr=DEVNULL, check=True)
				elif "zstd" in comp_type:
					run(["zstd", "-dc", str(comp_file)],
					    stdout=out_f, stderr=DEVNULL, check=True)
				else:
					out_f.close()
					decompressed.unlink(missing_ok=True)
					return
		except Exception:
			decompressed.unlink(missing_ok=True)
			return

		if not decompressed.is_file() or decompressed.stat().st_size == 0:
			return

		data = decompressed.read_bytes()
		decompressed.unlink(missing_ok=True)

		archives = _split_cpio_archives(data)
		if len(archives) < 2:
			return

		LOGI(f"vendor_boot v4: {len(archives)} concatenated CPIO archives found")

		# Identify recovery archives: those with props, recovery.fstab, or recovery RC files
		# Exclude base archives (those with only kernel modules / first_stage_ramdisk)
		recovery_archives = []
		for i, archive in enumerate(archives):
			has_prop = any(name in archive for name in _RECOVERY_PROP_NAMES)
			has_recovery_fstab = b'recovery.fstab' in archive
			has_recovery_rc = b'init.recovery.' in archive or b'.recovery.rc' in archive
			is_recovery = has_prop or has_recovery_fstab or has_recovery_rc
			if is_recovery:
				LOGI(f"  Archive {i}: recovery (prop={has_prop} fstab={has_recovery_fstab} rc={has_recovery_rc})")
				recovery_archives.append(archive)

		if not recovery_archives:
			return

		# Clear existing ramdisk and extract only recovery archives
		if self.ramdisk_path.is_dir():
			rmtree(self.ramdisk_path, ignore_errors=True)
		self.ramdisk_path.mkdir(parents=True, exist_ok=True)

		for archive in recovery_archives:
			run(["cpio", "-idm", "--no-absolute-filenames"],
			    input=archive, cwd=self.ramdisk_path, capture_output=True)

		LOGI("Recovery ramdisk selected for device tree generation")

	def repackimg(self):
		return self._execute_script("repack.sh")

	def cleanup(self):
		return self._execute_script("cleanup.sh")

	def _get_current_extracted_info(self, prefix: str):
		return AIKImageInfo(
			base_address=self._read_recovery_file(prefix, "base"),
			board_name=self._read_recovery_file(prefix, "board"),
			cmdline=self._read_recovery_file(prefix, "cmdline") \
				or self._read_recovery_file(prefix, "vendor_cmdline"),
			dt=self._get_extracted_info(prefix, "dt", check_size=True),
			dtb=self._get_extracted_info(prefix, "dtb", check_size=True),
			dtb_offset=self._read_recovery_file(prefix, "dtb_offset"),
			dtbo=self._get_extracted_info(prefix, "dtbo", check_size=True) \
				or self._get_extracted_info(prefix, "recovery_dtbo", check_size=True),
			header_version=self._read_recovery_file(prefix, "header_version", default="0"),
			image_type=self._read_recovery_file(prefix, "imgtype"),
			kernel=self._get_extracted_info(prefix, "kernel", check_size=True),
			kernel_offset=self._read_recovery_file(prefix, "kernel_offset"),
			origsize=self._read_recovery_file(prefix, "origsize"),
			os_version=self._read_recovery_file(prefix, "os_version"),
			pagesize=self._read_recovery_file(prefix, "pagesize"),
			ramdisk=self.ramdisk_path if self.ramdisk_path.is_dir() else None,
			ramdisk_compression=self._read_recovery_file(prefix, "ramdiskcomp") \
				or self._read_recovery_file(prefix, "vendor_ramdiskcomp"),
			ramdisk_offset=self._read_recovery_file(prefix, "ramdisk_offset"),
			sigtype=self._read_recovery_file(prefix, "sigtype"),
			tags_offset=self._read_recovery_file(prefix, "tags_offset"),
		)

	def _read_recovery_file(
		self, prefix: str, fragment: str, default: Optional[str] = None
	) -> Optional[str]:
		file = self._get_extracted_info(prefix, fragment)
		if not file:
			return default

		return file.read_text().splitlines()[0].strip()

	def _get_extracted_info(
		self, prefix: str, fragment: str, check_size: bool = False
	) -> Optional[Path]:
		path = self.images_path / f"{prefix}-{fragment}"

		if not path.is_file():
			return None

		try:
			if check_size and path.stat().st_size == 0:
				return None
		except Exception:
			return None

		return path

	def _execute_script(self, script: str, *args):
		command = [self.path / script, "--nosudo", *args]
		return check_output(command, stderr=STDOUT, universal_newlines=True, encoding="utf-8")
