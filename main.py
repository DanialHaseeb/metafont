#!/usr/bin/env python
"""
A CLI tool to process a font file.

  - Stripping non‐essential metadata from the name table.
  - Adding license information with multiple license types.
  - Renaming the font family and (optionally) the subfamily.
  - Adding manufacturer, designer, and trademark information.
  - Preserving the original version information.

Usage (non‐interactive):
    python font_tool.py input_font.otf "NewFamilyName" --subfamily "ExtraBold" --output output_font.otf --license OFL

Dependencies:
    - fontTools
    - Typer
    - Rich (for pretty CLI output)
    - uv (for environment/package management, as per your project setup)

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


def get_copyright_notice(manufacturer: Optional[str] = None) -> str:
    """Generate a copyright notice using the manufacturer name and current year."""
    current_year = datetime.datetime.now().year
    if manufacturer:
        return f"Copyright © {current_year} {manufacturer}. All Rights Reserved."
    return f"Copyright © {current_year}. All Rights Reserved."


@dataclass
class FontToolConfig:
    input_path: str
    new_family: str
    subfamily: Optional[str]
    output: Optional[str]
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

    - Replace Family (nameID 1) and Typographic Family (nameID 16) with new_family.
    - Replace Subfamily (nameID 2) if explicitly given, otherwise preserve the original.
    - Update Full Font Name (nameID 4) and PostScript Name (nameID 6) with new_family + subfamily.
    - Update license (nameIDs 13 and 14), manufacturer (8), designer (9), trademark (7),
      and copyright (0) as provided.
    - Preserve the original version string (nameID 5).
    - Strip any records not in the allowed list.
    """
    name_table = cast(table__n_a_m_e, font["name"])

    # Extract original version string and subfamily from the font.
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

    # If user provided a new subfamily, override the original; otherwise keep it.
    new_subfamily = config.subfamily if config.subfamily else original_subfamily

    def update_field(name_id: int, value: Optional[str]) -> None:
        # Remove existing records for nameID.
        name_table.names = [r for r in name_table.names if r.nameID != name_id]
        if value is not None and value != "":
            # platformID=3, platEncID=1, langID=0x409
            name_table.setName(value, name_id, 3, 1, 0x409)

    # Update Family Name (1) & Typographic Family (16) with new_family.
    for record in name_table.names:
        encoding = record.getEncoding()
        if record.nameID in (1, 16):
            record.string = config.new_family.encode(encoding)

    # Update subfamily (nameID 2) if user explicitly specified it.
    # If they didn't specify, we leave existing records as-is. But we do want to unify them
    # if there's a mismatch, so let's do an 'update' approach.
    if config.subfamily is not None:
        # Remove all existing nameID=2 records, set new one.
        update_field(2, new_subfamily)

    # Update Full Font Name (4).
    for record in name_table.names:
        if record.nameID == 4:
            encoding = record.getEncoding()
            record.string = f"{config.new_family} {new_subfamily}".encode(encoding)

    # Update PostScript Name (6).
    for record in name_table.names:
        if record.nameID == 6:
            encoding = record.getEncoding()
            ps_name = f"{config.new_family.replace(' ', '')}-{new_subfamily.replace(' ', '')}"
            record.string = ps_name.encode(encoding)

    # License handling
    if config.license_text is not None:
        # If a license text was explicitly provided (even as empty), use it.
        update_field(13, config.license_text)
        update_field(14, config.license_url)
    elif config.license_type is not None:
        # Use a known license or custom if the user provided text/URL.
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

    # Update manufacturer, designer, trademark
    if config.manufacturer is not None:
        update_field(8, config.manufacturer)
    if config.designer is not None:
        update_field(9, config.designer)
    update_field(7, config.trademark)  # trademark

    # Update copyright
    update_field(0, config.copyright_text)

    # Restore original version string if found
    if version_string:
        update_field(5, version_string)

    # Finally, filter out records not in our allowed set.
    name_table.names = [r for r in name_table.names if r.nameID in ALLOWED_NAME_IDS]


def interactive_mode() -> FontToolConfig:
    """
    Run interactive prompts for all required configuration values.
    For subfamily, the user may override the existing subfamily or leave blank to keep it.
    For other exception fields (license, trademark, copyright), pressing Enter removes it,
    typing 'keep' preserves the existing.
    """
    input_path = typer.prompt("Enter the path to the input font file")
    try:
        font = TTFont(input_path)
    except Exception as e:
        console.print(f"[bold red]Error opening font file:[/] {e}")
        sys.exit(1)

    # Helper to read a nameID
    def get_name_value(name_id: int) -> Optional[str]:
        for rec in font["name"].names:
            if rec.nameID == name_id:
                try:
                    return rec.toUnicode()
                except Exception:
                    pass
        return None

    existing_family = get_name_value(1) or "UnknownFamily"
    existing_subfamily = get_name_value(2) or "Regular"
    existing_manufacturer = get_name_value(8) or ""
    existing_designer = get_name_value(9) or ""
    existing_trademark = get_name_value(7) or ""
    existing_license_text = get_name_value(13) or ""
    existing_license_url = get_name_value(14) or ""
    existing_copyright = get_name_value(0) or ""

    # Prompt for new family
    new_family = typer.prompt("Enter new family name", default=existing_family)

    # Prompt for subfamily
    subfamily_input = typer.prompt(
        f"Enter subfamily (e.g. Regular, Bold) [leave blank to keep current: {existing_subfamily}]",
        default="",
    )
    # If user leaves it blank, we preserve existing subfamily.
    subfamily = subfamily_input if subfamily_input else None

    # Compute default output path
    used_subfamily = subfamily_input if subfamily_input else existing_subfamily
    postscript_name = f"{new_family.replace(' ', '')}-{used_subfamily.replace(' ', '')}"
    ext = os.path.splitext(input_path)[1]
    default_output = f"{postscript_name}{ext}"
    output = typer.prompt("Enter output file path", default=default_output)

    # License fields
    lic_input = typer.prompt(
        "Enter license type (OFL/Apache/MIT/Custom) [leave blank to remove, or type 'keep' to preserve existing]",
        default="OFL",
    )
    if lic_input.lower() == "keep":
        license_type = None
        license_text = existing_license_text
        license_url = existing_license_url
        custom_license = None
        custom_license_url = None
    elif lic_input == "":
        license_type = None
        license_text = ""
        license_url = ""
        custom_license = None
        custom_license_url = None
    else:
        try:
            license_type = LicenseType(lic_input.upper())
        except ValueError:
            console.print("[bold red]Invalid license type.[/] Defaulting to OFL.")
            license_type = LicenseType.OFL
        if license_type == LicenseType.CUSTOM:
            custom_license = typer.prompt(
                "Enter custom license text [leave blank to remove, or type 'keep' to preserve existing]",
                default="",
            )
            if custom_license.lower() == "keep":
                custom_license = existing_license_text
            custom_license_url = typer.prompt(
                "Enter custom license URL [leave blank to remove, or type 'keep' to preserve existing]",
                default="",
            )
            if custom_license_url.lower() == "keep":
                custom_license_url = existing_license_url
            license_text = None
            license_url = None
        else:
            custom_license = None
            custom_license_url = None
            lic_info = LICENSE_INFO.get(license_type)
            license_text = lic_info["text"] if lic_info else ""
            license_url = lic_info["url"] if lic_info else ""

    # Non-exception fields
    manufacturer = typer.prompt("Enter manufacturer name", default=existing_manufacturer)
    designer = typer.prompt("Enter designer name", default=existing_designer)

    # Trademark
    trademark_prompt = (
        f"Enter trademark text [blank to remove, 'keep' to preserve (current: {existing_trademark})]"
    )
    trademark = typer.prompt(trademark_prompt, default="")
    if trademark.lower() == "keep":
        trademark = existing_trademark

    # Copyright
    copyright_prompt = (
        f"Enter copyright notice [blank to remove, 'keep' to preserve (current: {existing_copyright})]"
    )
    c_text = typer.prompt(copyright_prompt, default="")
    if c_text.lower() == "keep":
        c_text = existing_copyright

    return FontToolConfig(
        input_path=input_path,
        new_family=new_family,
        subfamily=subfamily,
        output=output,
        license_type=license_type,
        custom_license=custom_license,
        custom_license_url=custom_license_url,
        license_text=license_text,
        license_url=license_url,
        manufacturer=manufacturer,
        designer=designer,
        trademark=trademark,
        copyright_text=c_text,
    )


def process_font_with_config(config: FontToolConfig) -> None:
    """Open the font, update its metadata using the provided config, and save the output."""
    try:
        console.print(f"Opening font file: [bold]{config.input_path}[/]")
        font = TTFont(config.input_path)
    except Exception as e:
        console.print(f"[bold red]Error opening font file:[/] {e}")
        sys.exit(1)

    console.print(
        f"Updating metadata with new family name: [bold]{config.new_family}[/]"
    )
    if config.subfamily:
        console.print(f"Using user-specified subfamily: [bold]{config.subfamily}[/]")
    else:
        console.print("No new subfamily specified; original subfamily is preserved.")

    update_font_metadata(font, config)

    # Output with absolute path for clarity
    output_path = os.path.abspath(config.output) if config.output else None
    try:
        console.print(f"Saving processed font to: [bold]{output_path}[/]")
        font.save(output_path)
        console.print("[bold green]Success![/] Font processing completed.")
    except Exception as e:
        console.print(f"[bold red]Error saving font file:[/] {e}")
        sys.exit(1)


@app.command()
def process_font(
    input_path: str = typer.Argument(
        ..., help="Path to the input .otf or .ttf font file."
    ),
    new_family: str = typer.Argument(..., help="New font family name."),
    subfamily: Optional[str] = typer.Option(
        None,
        "--subfamily",
        "-s",
        help="Optionally specify a new subfamily (e.g. Bold, ExtraLight). If omitted, uses the existing subfamily.",
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
        None, "--custom-license", help="Custom license text (used when --license is 'Custom')"
    ),
    custom_license_url: Optional[str] = typer.Option(
        None, "--custom-license-url", help="Custom license URL (used when --license is 'Custom')"
    ),
    manufacturer: Optional[str] = typer.Option(
        None,
        "--manufacturer",
        "-m",
        help="Manufacturer name to add to the font. (If not provided, the existing value is preserved.)",
    ),
    designer: Optional[str] = typer.Option(
        None,
        "--designer",
        "-d",
        help="Designer name to add to the font. (If not provided, the existing value is preserved.)",
    ),
    trademark: Optional[str] = typer.Option(
        None,
        "--trademark",
        "-t",
        help="Trademark text to add to the font. (If not provided, the field will remain unchanged.)",
    ),
    copyright_text: Optional[str] = typer.Option(
        None,
        "--copyright",
        "-c",
        help="Copyright notice to add to the font. (If not provided, defaults to a manufacturer-based notice.)",
    ),
):
    """
    Process the font file by stripping non-essential metadata, adding license/subfamily/manufacturer/designer
    data, and renaming the font family.
    """
    # First open the font to get its existing subfamily if needed.
    try:
        font = TTFont(input_path)
    except Exception as e:
        typer.echo(f"Error opening font file '{input_path}': {e}")
        raise typer.Exit(code=1)

    # Read the original subfamily to compute a default output file name if one isn't provided.
    orig_subfamily = "Regular"
    for rec in font["name"].names:
        if rec.nameID == 2:
            try:
                orig_subfamily = rec.toUnicode()
            except Exception:
                pass
            break

    used_subfamily = subfamily if subfamily else orig_subfamily

    # Compute default output name if not provided
    postscript_name = (
        f"{new_family.replace(' ', '')}-{used_subfamily.replace(' ', '')}"
    )
    ext = os.path.splitext(input_path)[1]
    if not output:
        output = f"{postscript_name}{ext}"

    # Prepare license text/URL
    lic_text: Optional[str] = None
    lic_url: Optional[str] = None
    if license_type == LicenseType.CUSTOM:
        if not (custom_license and custom_license_url):
            typer.echo(
                "Custom license requires both --custom-license and --custom-license-url."
            )
            raise typer.Exit(code=1)
        lic_text = custom_license
        lic_url = custom_license_url
    else:
        lic_info = LICENSE_INFO.get(license_type)
        lic_text = lic_info["text"] if lic_info else ""
        lic_url = lic_info["url"] if lic_info else ""

    # Default copyright if none given.
    if copyright_text is None:
        # Only set a default if manufacturer is provided
        if manufacturer:
            copyright_text = get_copyright_notice(manufacturer)
        else:
            copyright_text = None

    config = FontToolConfig(
        input_path=input_path,
        new_family=new_family,
        subfamily=subfamily,
        output=output,
        license_type=license_type,
        custom_license=custom_license,
        custom_license_url=custom_license_url,
        license_text=lic_text,
        license_url=lic_url,
        manufacturer=manufacturer,
        designer=designer,
        trademark=trademark,
        copyright_text=copyright_text,
    )
    process_font_with_config(config)


if __name__ == "__main__":
    # If no arguments are passed, run in interactive mode.
    if len(sys.argv) == 1:
        config = interactive_mode()
        process_font_with_config(config)
    else:
        app()
