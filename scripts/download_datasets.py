"""
Dataset downloader for GraphRL-Sec.

Downloads UNSW-NB15 (~2 GB) and CICIDS2017 (~7 GB) from Kaggle.

Prerequisites:
    1. Create a free Kaggle account at https://www.kaggle.com
    2. Go to https://www.kaggle.com/settings  →  API  →  Create New Token
    3. Save the downloaded kaggle.json to C:\\Users\\<you>\\.kaggle\\kaggle.json
    4. Run:  python scripts/download_datasets.py

Usage:
    python scripts/download_datasets.py                  # download both
    python scripts/download_datasets.py --dataset unsw   # UNSW-NB15 only
    python scripts/download_datasets.py --dataset cicids # CICIDS2017 only
    python scripts/download_datasets.py --verify         # verify existing files
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from typing import NamedTuple

import click

# Force UTF-8 output so Unicode symbols work on Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Dataset specs
# ---------------------------------------------------------------------------

RAW_DIR = Path("data/raw")

# Kaggle dataset slug + expected output directory after unzip
class DatasetSpec(NamedTuple):
    key:         str          # CLI key used with --dataset flag
    slug:        str          # Kaggle dataset slug  owner/name
    dest_dir:    Path         # where to place the extracted CSVs
    description: str
    min_size_mb: int          # minimum expected total size after download


_DATASETS: list[DatasetSpec] = [
    DatasetSpec(
        key         = "unsw",
        slug        = "mrwellsdavid/unsw-nb15",
        dest_dir    = RAW_DIR / "unsw",
        description = "UNSW-NB15 (~2 GB, 4 CSV files, Unix timestamps)",
        min_size_mb = 550,
    ),
    DatasetSpec(
        key         = "cicids",
        slug        = "chethuhn/network-intrusion-dataset",
        dest_dir    = RAW_DIR / "cicids",
        description = "CICIDS2017 (~7 GB, one CSV per day of the week)",
        min_size_mb = 500,
    ),
]

_DATASETS_BY_KEY: dict[str, DatasetSpec] = {d.key: d for d in _DATASETS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_kaggle_credentials() -> None:
    """Raise SystemExit with instructions if kaggle.json is missing."""
    cred_path = Path.home() / ".kaggle" / "kaggle.json"
    if not cred_path.exists():
        click.echo(
            click.style("\n[ERROR] Kaggle credentials not found.\n", fg="red"),
            err=True,
        )
        click.echo(
            "  1. Create a free account at  https://www.kaggle.com\n"
            "  2. Go to  https://www.kaggle.com/settings  →  API  →  Create New Token\n"
            f"  3. Save the downloaded kaggle.json to:\n"
            f"       {cred_path}\n"
            "  4. Re-run this script.\n",
            err=True,
        )
        sys.exit(1)
    # Kaggle SDK reads credentials lazily — just check file exists here.


def _human_mb(path: Path) -> float:
    """Return total size of all files under path in megabytes."""
    if path.is_file():
        return path.stat().st_size / 1_048_576
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1_048_576


def _patch_kaggle_ssl() -> None:
    """
    Disable SSL verification on the Kaggle SDK's internal requests session.

    Required on networks where a corporate/ISP proxy performs SSL inspection
    and presents a self-signed certificate that Python's ssl module rejects.
    This is safe for downloading public datasets.
    """
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Patch requests so all outgoing calls skip cert verification
    import requests
    original_send = requests.Session.send

    def _send_no_verify(self: requests.Session, *args: object, **kwargs: object) -> requests.Response:  # type: ignore[override]
        kwargs["verify"] = False
        return original_send(self, *args, **kwargs)  # type: ignore[arg-type]

    requests.Session.send = _send_no_verify  # type: ignore[method-assign]


def _download_dataset(spec: DatasetSpec, tmp_dir: Path) -> None:
    """
    Download and extract one Kaggle dataset.

    Uses the Kaggle Python SDK so progress bars appear automatically.
    The zip is placed in tmp_dir, extracted to spec.dest_dir, then removed.
    """
    import kaggle  # imported late — allows credential error to surface cleanly

    _patch_kaggle_ssl()
    spec.dest_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    click.echo(
        click.style(f"\n→ Downloading {spec.description}", fg="cyan")
    )
    click.echo(f"  Kaggle slug : {spec.slug}")
    click.echo(f"  Destination : {spec.dest_dir}")

    # Download zip into tmp_dir
    kaggle.api.dataset_download_files(
        spec.slug,
        path=str(tmp_dir),
        unzip=False,      # we handle extraction ourselves for better logging
        quiet=False,      # show Kaggle's own progress output
    )

    # Find the downloaded zip (Kaggle names it <dataset-name>.zip)
    zips = list(tmp_dir.glob("*.zip"))
    if not zips:
        click.echo(click.style("[ERROR] No zip found after download.", fg="red"), err=True)
        sys.exit(1)

    zip_path = zips[0]
    click.echo(f"\n  Extracting {zip_path.name} → {spec.dest_dir} …")

    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.namelist()
        csv_members = [m for m in members if m.lower().endswith(".csv")]
        click.echo(f"  Found {len(csv_members)} CSV file(s) in archive.")
        zf.extractall(spec.dest_dir)

    zip_path.unlink()   # free disk space immediately
    click.echo(click.style(f"  ✓ Extracted to {spec.dest_dir}", fg="green"))


def _verify_dataset(spec: DatasetSpec) -> bool:
    """
    Check that the expected CSVs exist and total size meets the minimum.

    Returns True if valid, False otherwise.
    """
    if not spec.dest_dir.exists():
        click.echo(
            click.style(f"  ✗ {spec.key.upper()}: directory not found — {spec.dest_dir}", fg="red")
        )
        return False

    csvs = list(spec.dest_dir.rglob("*.csv"))
    if not csvs:
        click.echo(
            click.style(f"  ✗ {spec.key.upper()}: no CSV files found in {spec.dest_dir}", fg="red")
        )
        return False

    total_mb = _human_mb(spec.dest_dir)
    ok = total_mb >= spec.min_size_mb
    icon  = click.style("  ✓", fg="green") if ok else click.style("  ✗", fg="red")
    label = f"{spec.key.upper()} ({len(csvs)} CSVs, {total_mb:,.0f} MB)"

    if ok:
        click.echo(f"{icon} {label}")
    else:
        click.echo(
            f"{icon} {label}  "
            f"[expected ≥ {spec.min_size_mb:,} MB — download may be incomplete]"
        )

    for csv in sorted(csvs):
        size_mb = _human_mb(csv)
        click.echo(f"       {csv.name:<55} {size_mb:>8.1f} MB")

    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--dataset",
    type=click.Choice(["unsw", "cicids", "all"], case_sensitive=False),
    default="all",
    show_default=True,
    help="Which dataset to download.",
)
@click.option(
    "--verify",
    is_flag=True,
    default=False,
    help="Only verify existing files — do not download.",
)
@click.option(
    "--tmp-dir",
    type=click.Path(path_type=Path),
    default=Path("data/.download_tmp"),
    show_default=True,
    help="Temporary directory for zip files during extraction.",
)
def main(dataset: str, verify: bool, tmp_dir: Path) -> None:
    """Download full UNSW-NB15 and CICIDS2017 datasets from Kaggle."""

    targets = (
        list(_DATASETS_BY_KEY.values())
        if dataset == "all"
        else [_DATASETS_BY_KEY[dataset]]
    )

    if verify:
        click.echo(click.style("\nVerifying dataset files …\n", bold=True))
        all_ok = all(_verify_dataset(spec) for spec in targets)
        if all_ok:
            click.echo(click.style("\nAll datasets verified ✓\n", fg="green", bold=True))
        else:
            click.echo(
                click.style("\nSome datasets are missing or incomplete.\n", fg="yellow")
                + "Run without --verify to download them.\n"
            )
            sys.exit(1)
        return

    # Download mode
    _check_kaggle_credentials()

    click.echo(click.style("\nGraphRL-Sec Dataset Downloader", bold=True))
    click.echo(f"Downloading: {', '.join(s.key.upper() for s in targets)}\n")

    for spec in targets:
        _download_dataset(spec, tmp_dir)

    # Clean up tmp dir if empty
    if tmp_dir.exists() and not any(tmp_dir.iterdir()):
        tmp_dir.rmdir()

    # Verify everything downloaded correctly
    click.echo(click.style("\nVerification …", bold=True))
    all_ok = all(_verify_dataset(spec) for spec in targets)

    if all_ok:
        click.echo(
            click.style("\n✓ All datasets downloaded and verified.\n", fg="green", bold=True)
        )
        click.echo("Next steps:")
        click.echo(
            "  python -m src.ingestion.cli ingest "
            "--dataset unsw --path data/raw/unsw/ --mode batch"
        )
    else:
        click.echo(
            click.style("\n⚠ Some files look incomplete. Re-run to retry.\n", fg="yellow")
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
