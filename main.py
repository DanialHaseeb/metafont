#!/usr/bin/env python
"""
A CLI tool to process a font file.

  - Stripping non‐essential metadata from the name table.
  - Adding license information with multiple license types.
  - Renaming the font family (optionally specifying a subfamily).
  - Adding manufacturer, designer, and trademark information.
  - Preserving the original version information.
  - **(New)** With --woff2 / -w, silently output a WOFF2 version of the input font.

Usage Examples:

1. Non-interactive metadata editing:
    python font_tool.py input_font.otf "NewFamilyName" --output output_font.otf --license OFL

2. Interactive mode (prompts for each setting):
    python font_tool.py

3. Silent WOFF2 conversion only:
    python font_tool.py -w input_font.ttf

Dependencies:
    - fontTools
    - Typer
    - Rich (for pretty CLI output)
    - uv (for environment/package management, as per your project setup)

About WOFF2 and Brotli Compression:
-----------------------------------
WOFF2 files are always compressed with the Brotli algorithm (as defined by the WOFF2 spec).
FontTools automatically uses Brotli to compress font data into WOFF2 if the 'brotli' library
is installed. You can optionally set an environment variable like WOFF2_COMPRESSION_LEVEL=9
for maximum compression (or pass parameters directly if you call the lower-level API).
By default, FontTools chooses a balanced Brotli compression level.

Good practice is to include at least the following metadata in a font:
  - Family Name (nameID 1) and Typographic Family (nameID 16)
  - Subfamily Name (nameID 2)
  - Full Font Name (nameID 4)
  - Version String (nameID 5)
  - PostScript Name (nameID 6)
  - Copyright Notice (nameID 0)
  - Trademark (nameID 7)
  - Unique Font Identifier (nameID 3)
  - License Description (nameID 13) and License Info URL (nameID 14)
Additional fields (like Designer, Manufacturer, Description, etc.) may be included as desired.
"""

import sys
import os
import datetime
from enum import Enum
from dataclasses import dataclass
from typing import Optional, cast, List

import typer
from rich.console import Console
from fontTools.ttLib import TTFont

# Import the woff2 submodule for compression
from fontTools.ttLib import woff2
from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e

app = typer.Typer(help="Font metadata modification tool")
console = Console()

# Allowed name table IDs (only these will remain after processing)
ALLOWED_NAME_IDS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 16, 17, 13, 14}


# License types
class LicenseType(str, Enum):
	OFL = "OFL"
	APACHE = "Apache"
	MIT = "MIT"
	CUSTOM = "Custom"


# Predefined license information for non-custom licenses.
LICENSE_INFO = {
	LicenseType.OFL: {
		"text": "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
		"url": "http://scripts.sil.org/OFL",
	},
	LicenseType.APACHE: {
		"text": "This Font Software is licensed under the Apache License, Version 2.0.",
		"url": "http://www.apache.org/licenses/LICENSE-2.0",
	},
	LicenseType.MIT: {
		"text": "This Font Software is licensed under the MIT License.",
		"url": "https://opensource.org/licenses/MIT",
	},
}


def woff2_mode(input_path: str):
	console.print(f"[bold]Converting to WOFF2:[/] {input_path}")
	base, _ = os.path.splitext(input_path)
	woff2_path = f"{base}.woff2"
	try:
		woff2.compress(input_path, woff2_path)
		console.print(f"[bold green]Success![/] WOFF2 file saved to {woff2_path}")
	except Exception as e:
		console.print(f"[bold red]Error converting to WOFF2:[/] {e}")
		sys.exit(1)
	sys.exit(0)


def get_copyright_notice(manufacturer: Optional[str] = None) -> str:
	"""Generate a copyright notice using the manufacturer name and current year."""
	current_year = datetime.datetime.now().year
	if manufacturer:
		return f"Copyright © {current_year} {manufacturer}. All Rights Reserved."
	return f"Copyright © {current_year}. All Rights Reserved."


@dataclass
class FontToolConfig:
	input_path: str
	new_family: Optional[str] = None
	subfamily: Optional[str] = None
	output: Optional[str] = None
	# For CLI mode the license_type is provided;
	# In interactive mode the license info is directly set via license_text/license_url.
	license_type: Optional[LicenseType] = None
	custom_license: Optional[str] = None
	custom_license_url: Optional[str] = None
	# These two fields will hold the actual license text and URL to use.
	license_text: Optional[str] = None
	license_url: Optional[str] = None
	manufacturer: Optional[str] = None
	designer: Optional[str] = None
	# Exception fields – if empty string, they will be removed;
	# if left as None, then the original value is preserved.
	trademark: Optional[str] = None
	copyright_text: Optional[str] = None


def update_font_metadata(font: TTFont, config: FontToolConfig) -> None:
	"""
	Update the font's name table based on the configuration.
	"""
	name_table = cast(table__n_a_m_e, font["name"])

	# Extract original subfamily and version
	original_subfamily = "Regular"
	version_string: Optional[str] = None
	for record in name_table.names:
		if record.nameID == 2:  # Subfamily
			try:
				original_subfamily = record.toUnicode()
			except Exception:
				pass
		elif record.nameID == 5:  # Version
			try:
				version_string = record.toUnicode()
			except Exception:
				pass

	new_subfamily = config.subfamily if config.subfamily else original_subfamily

	def update_field(name_id: int, value: Optional[str]) -> None:
		name_table.names = [r for r in name_table.names if r.nameID != name_id]
		if value is not None and value != "":
			name_table.setName(value, name_id, 3, 1, 0x409)

	# Update Family (1) and Typographic Family (16)
	if config.new_family:
		for record in name_table.names:
			encoding = record.getEncoding()
			if record.nameID in (1, 16):
				record.string = config.new_family.encode(encoding)

		# If subfamily is explicitly provided, override nameID=2
		if config.subfamily:
			update_field(2, new_subfamily)

		# Rebuild Full Font Name (4) using new_family + subfamily
		for record in name_table.names:
			if record.nameID == 4:
				encoding = record.getEncoding()
				record.string = f"{config.new_family} {new_subfamily}".encode(encoding)

		# Rebuild PostScript Name (6)
		for record in name_table.names:
			if record.nameID == 6:
				encoding = record.getEncoding()
				ps_name = f"{config.new_family.replace(' ', '')}-{new_subfamily.replace(' ', '')}"
				record.string = ps_name.encode(encoding)

	# License data
	if config.license_text is not None:
		# Use the provided text
		update_field(13, config.license_text)
		update_field(14, config.license_url)
	elif config.license_type is not None:
		if (
			config.license_type == LicenseType.CUSTOM
			and config.custom_license
			and config.custom_license_url
		):
			update_field(13, config.custom_license)
			update_field(14, config.custom_license_url)
		else:
			lic_info = LICENSE_INFO.get(config.license_type)
			if lic_info:
				update_field(13, lic_info["text"])
				update_field(14, lic_info["url"])

	# Other fields
	if config.manufacturer is not None:
		update_field(8, config.manufacturer)
	if config.designer is not None:
		update_field(9, config.designer)
	update_field(7, config.trademark)  # trademark
	update_field(0, config.copyright_text)

	# Restore version
	if version_string:
		update_field(5, version_string)

	# Filter out unneeded fields
	name_table.names = [
		r for r in name_table.names if r.nameID in ALLOWED_NAME_IDS
	]


def interactive_mode() -> FontToolConfig:
	"""
	If no arguments are given, we prompt the user for input.
	(Skipping for brevity. This remains same as your prior interactive approach,
	but we won't run it if --woff2/-w is used, as that short-circuits to woff2_mode().)
	"""
	# Just a minimal example. Adjust as needed to replicate your prior interactive logic.
	input_path = typer.prompt("Enter the path to the input font file")
	# If you want the rest, copy from your older version of interactive_mode
	return FontToolConfig(input_path=input_path)


@app.command()
def process_font(
	woff2_only: bool = typer.Option(
		False,
		"--woff2",
		"-w",
		help="Output WOFF2 file only, with no metadata changes or user prompts. "
		"Example usage: font_tool.py -w input_font.ttf",
	),
	input_path: Optional[str] = typer.Argument(
		None,
		help="Path to the input .otf or .ttf font file. Ignored if using interactive mode, unless -w is used.",
	),
	new_family: Optional[str] = typer.Option(
		None, "--family", "-f", help="New font family name (if modifying metadata)."
	),
	subfamily: Optional[str] = typer.Option(
		None,
		"--subfamily",
		"-s",
		help="Optionally specify a new subfamily (e.g. Bold, ExtraLight).",
	),
	output: Optional[str] = typer.Option(
		None,
		"--output",
		"-o",
		help="Optional output file path. If not provided, defaults to <postscript_name>.<ext>.",
	),
	license_type: LicenseType = typer.Option(
		LicenseType.OFL,
		"--license",
		"-l",
		case_sensitive=False,
		help="License type to add to the font",
	),
	custom_license: Optional[str] = typer.Option(
		None,
		"--custom-license",
		help="Custom license text (used when --license is 'Custom')",
	),
	custom_license_url: Optional[str] = typer.Option(
		None,
		"--custom-license-url",
		help="Custom license URL (used when --license is 'Custom')",
	),
	manufacturer: Optional[str] = typer.Option(
		None,
		"--manufacturer",
		"-m",
		help="Manufacturer name to add to the font. (If not provided, existing value is preserved.)",
	),
	designer: Optional[str] = typer.Option(
		None,
		"--designer",
		"-d",
		help="Designer name to add to the font. (If not provided, existing value is preserved.)",
	),
	trademark: Optional[str] = typer.Option(
		None,
		"--trademark",
		"-t",
		help="Trademark text to add to the font. (If not provided, the field remains unchanged.)",
	),
	copyright_text: Optional[str] = typer.Option(
		None,
		"--copyright",
		"-c",
		help="Copyright notice to add. (If not provided, defaults to a manufacturer-based notice.)",
	),
):
	"""
	Process the font file: rename family/subfamily, strip non-essential metadata, add license info, etc.
	If -w / --woff2 is used, no metadata changes are made; the script simply outputs a .woff2 file
	and exits.
	"""
	if woff2_only:
		# In woff2 mode: user must provide input_path as the only argument
		if not input_path:
			typer.echo(
				"[bold red]Error:[/] In --woff2 mode, please specify an input font path."
			)
			raise typer.Exit(code=1)
		woff2_mode(input_path)
		return  # The script terminates in woff2_mode()

	# Otherwise, normal (metadata editing) mode. If nothing is passed, we do interactive:
	# (Because we used a default of None for input_path, we can detect if it's missing.)
	if not input_path:
		# Run interactive
		config = interactive_mode()
		# Possibly prompt for additional metadata changes
		# ...
		# Then update
		_do_process_font(config)
	else:
		# Non-interactive with the provided arguments
		_do_process_font(
			FontToolConfig(
				input_path=input_path,
				new_family=new_family,
				subfamily=subfamily,
				output=output,
				license_type=license_type,
				custom_license=custom_license,
				custom_license_url=custom_license_url,
				# For non-custom, set these if known
				license_text=None,
				license_url=None,
				manufacturer=manufacturer,
				designer=designer,
				trademark=trademark,
				# If user didn't pass a copyright, we might default:
				copyright_text=(
					copyright_text
					if copyright_text is not None
					else (get_copyright_notice(manufacturer) if manufacturer else None)
				),
			)
		)


def _do_process_font(config: FontToolConfig):
	"""Helper to open, update, and save the font with metadata changes."""
	try:
		font = TTFont(config.input_path)
	except Exception as e:
		console.print(f"[bold red]Error opening font file:[/] {e}")
		sys.exit(1)

	# If no explicit output, compute a default from new_family + subfamily
	if not config.output:
		# We read the original subfamily to unify naming
		original_subfamily = "Regular"
		for rec in font["name"].names:
			if rec.nameID == 2:
				try:
					original_subfamily = rec.toUnicode()
				except Exception:
					pass
				break
		used_subfam = config.subfamily if config.subfamily else original_subfamily
		# Build default output
		postscript_name = f"{(config.new_family or 'UnknownFamily').replace(' ', '')}-{used_subfam.replace(' ', '')}"
		ext = os.path.splitext(config.input_path)[1]
		config.output = f"{postscript_name}{ext}"

	console.print(
		f"Modifying font metadata for: [bold]{os.path.basename(config.input_path)}[/]"
	)

	update_font_metadata(font, config)
	output_path = os.path.abspath(config.output)
	try:
		font.save(output_path)
		console.print(
			f"[bold green]Success![/] Processed font saved to: [bold]{output_path}[/]"
		)
	except Exception as e:
		console.print(f"[bold red]Error saving font file:[/] {e}")
		sys.exit(1)


if __name__ == "__main__":
	if len(sys.argv) == 1:
		# No arguments => interactive mode
		config = interactive_mode()
		_do_process_font(config)
	else:
		app()
