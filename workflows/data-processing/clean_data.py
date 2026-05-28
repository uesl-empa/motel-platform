"""Minimal data cleaning scaffold for MOTEL workflows."""

from pathlib import Path

import pandas as pd


def clean_csv(input_path: Path, output_path: Path) -> None:
    df = pd.read_csv(input_path)
    df.columns = [c.strip().lower() for c in df.columns]
    df.to_csv(output_path, index=False)


if __name__ == "__main__":
    src = Path("data/technologies/conversion.csv")
    dst = Path("data/technologies/conversion.cleaned.csv")
    clean_csv(src, dst)
    print(f"Wrote cleaned file to {dst}")
