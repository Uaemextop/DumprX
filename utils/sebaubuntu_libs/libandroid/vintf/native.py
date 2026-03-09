#
# Copyright (C) 2022 Sebastiano Barezzi
#
# SPDX-License-Identifier: Apache-2.0
#

from typing import Optional
from textwrap import indent
from xml.etree.ElementTree import Element

from sebaubuntu_libs.libandroid.vintf import INDENTATION
from sebaubuntu_libs.libandroid.vintf.common import Hal

class NativeHal(Hal):
	"""Class representing a native HAL."""
	def __init__(self, name: str, version: Optional[str] = None):
		"""Initialize an object."""
		super().__init__(name)

		self.version = version

	def __str__(self) -> str:
		string = '<hal format="native">\n'
		string += indent(f'<name>{self.name}</name>\n', INDENTATION)
		if self.version is not None:
			string += indent(f'<version>{self.version}</version>\n', INDENTATION)
		string += '</hal>'

		return string

	@classmethod
	def from_entry(cls, entry: Element) -> 'NativeHal':
		"""Create a native HAL from a VINTF entry."""
		name = entry.findtext("name")
		assert name is not None, "Missing name in native HAL"

		version = entry.findtext("version")

		return cls(name, version)
