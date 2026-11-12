import argparse


class OptionHelp(argparse.HelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> str:
        said = action.help or ""
        if action.required and action.option_strings:
            return f"{said} (required)"
        if action.nargs != 0 and action.default not in (None, "", argparse.SUPPRESS):
            return f"{said} (default: %(default)s)"
        return said
