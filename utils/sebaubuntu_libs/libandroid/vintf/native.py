#
# Copyright (C) 2022 Sebastiano Barezzi
#
# SPDX-License-Identifier: Apache-2.0
#

from textwrap import indent
from typing import Optional
from xml.etree.ElementTree import Element

from sebaubuntu_libs.libandroid.vintf import INDENTATION
from sebaubuntu_libs.libandroid.vintf.common import Hal

class NativeHal(Hal):
	"""Class representing a native HAL."""
	def __init__(self, name: str, version: Optional[str] = None):
		"""Initialize an object."""
		super().__init__(name)

		self.version = version

	def __eq__(self, __o: object) -> bool:
		if isinstance(__o, NativeHal):
			return (self.name == __o.name
			        and self.version == __o.version)
		return False

	def __hash__(self) -> int:
		return hash((self.name, self.version))

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
		assert entry.get("format") == "native"

		name = entry.findtext("name")
		assert name is not None, "Missing name in native HAL"

		version = entry.findtext("version")

		return cls(name, version)
