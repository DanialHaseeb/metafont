# Metafont

A powerful command-line interface (CLI) tool built in Python to simplify font metadata manipulation. This tool allows you to easily:

- Strip non-essential metadata from font files (OTF/TTF)
- Add and customize font license information
- Rename the font family
- Insert or update manufacturer, designer, and trademark details
- Preserve the original font version

## Features

- **Interactive Mode**: Prompts users for input if arguments are not provided.
- **Metadata Management**: Customize font metadata such as manufacturer, designer, license information, and trademarks.
- **Multiple Licenses Support**: Supports SIL Open Font License (OFL), Apache License, MIT License, and custom licenses.
- **Robust CLI**: Built with Typer for clear and easy command-line usage and Rich for beautiful output formatting.

## Good Practices for Font Metadata

It is recommended to include the following metadata fields:

- Family Name (`nameID 1`) and Typographic Family (`nameID 16`)
- Subfamily Name (`nameID 2`)
- Full Font Name (`nameID 4`)
- Version String (`nameID 5`)
- PostScript Name (`nameID 6`)
- Copyright Notice (`nameID 0`)
- Trademark (`nameID 7`)
- Unique Font Identifier (`nameID 3`)
- License Description (`nameID 13`) and License Info URL (`nameID 14`)

Additional recommended metadata:

- Manufacturer (`nameID 8`)
- Designer (`nameID 9`)

## Dependencies

- [fontTools](https://github.com/fonttools/fonttools): For font file manipulation
- [Typer](https://typer.tiangolo.com/): For building the CLI
- [Rich](https://rich.readthedocs.io/) for user-friendly CLI output

## License

This tool is provided under the MIT License.
