"""Entry point: `python -m soundboard`."""

from __future__ import annotations

import argparse

from .config import DEFAULT_CONFIG_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description="Customizable software soundboard")
    parser.add_argument(
        "-c",
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="Print available audio devices and exit",
    )
    args = parser.parse_args()

    if args.list_devices:
        from .audio_engine import list_devices

        for d in list_devices():
            io = []
            if d["max_input_channels"]:
                io.append(f"in:{d['max_input_channels']}")
            if d["max_output_channels"]:
                io.append(f"out:{d['max_output_channels']}")
            print(f"[{d['index']:>2}] {d['name']}  ({', '.join(io)})")
        return

    from .gui import run

    run(args.config)


if __name__ == "__main__":
    main()
