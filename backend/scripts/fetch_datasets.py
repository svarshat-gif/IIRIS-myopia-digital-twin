"""Download public research files; --offline verifies an existing raw directory.

Never substitutes generated data. Metadata and repository checksums are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import urlopen

RAW = Path(__file__).resolve().parents[1] / "data/raw"
SOURCES = {
    "dryad_3year": ("10.5061/dryad.d4mb3pn", "Data3.xlsx", "https://datadryad.org/downloads/file_stream/170312"),
    "dims": ("10.5281/zenodo.18166476", "DataSet.xlsx", "https://zenodo.org/api/records/18166476/files/DataSet.xlsx/content"),
    "shanghai": ("10.5061/dryad.c2fqz615c", "DATA.xls", "https://datadryad.org/downloads/file_stream/475629"),
}


def get(url: str) -> bytes:
    with urlopen(url, timeout=40) as response:
        return response.read()


def fetch(raw: Path = RAW, offline: bool = False, sources: list[str] | None = None) -> dict:
    manifest = {}
    for name, (doi, filename, url) in SOURCES.items():
        if sources and name not in sources:
            continue
        folder = raw / name
        folder.mkdir(parents=True, exist_ok=True)
        bundled = Path(__file__).resolve().parents[1] / "data/open" / name
        for filename_to_copy in (filename, "metadata.json", "files.json"):
            if not (folder / filename_to_copy).exists() and (bundled / filename_to_copy).exists():
                shutil.copyfile(bundled / filename_to_copy, folder / filename_to_copy)
        metadata_path = folder / "metadata.json"
        metadata_url = ("https://zenodo.org/api/records/18166476" if name == "dims" else
                        "https://datadryad.org/api/v2/datasets/doi%3A" + doi.replace("/", "%2F"))
        try:
            if not offline:
                metadata_path.write_bytes(get(metadata_url))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
            license_id = metadata["metadata"]["license"]["id"] if name == "dims" else metadata["license"]
            expected_license = "cc-by-4.0" if name == "dims" else "https://spdx.org/licenses/CC0-1.0.html"
            if license_id != expected_license:
                raise ValueError(f"Unreviewed license: {license_id}")
            path = folder / filename
            if not path.exists() and not offline:
                path.write_bytes(get(url))
            data = path.read_bytes()
            if name == "dims":
                expected = metadata["files"][0]["checksum"]
            else:
                files_path = folder / "files.json"
                if not offline:
                    version_url = "https://datadryad.org" + metadata["_links"]["stash:version"]["href"] + "/files"
                    files_path.write_bytes(get(version_url))
                files = json.loads(files_path.read_text(encoding="utf-8-sig"))["_embedded"]["stash:files"]
                file = next(f for f in files if f["path"].lower() == filename.lower())
                expected = file["digestType"].lower().replace("-", "") + ":" + file["digest"]
            algorithm, digest = expected.split(":", 1)
            if hashlib.new(algorithm, data).hexdigest() != digest:
                raise ValueError(f"Repository checksum mismatch: {path}")
            manifest[name] = {"doi": doi, "file": filename, "license": license_id,
                              "repository_checksum": expected, "sha256": hashlib.sha256(data).hexdigest()}
        except Exception as exc:
            raise RuntimeError(f"Cannot verify {name}: {exc}. Download {url} to {folder / filename}; "
                               f"save {metadata_url} as metadata.json. Dryad also needs its version /files "
                               "response as files.json. Then rerun --offline. No synthetic fallback.") from exc
    (raw / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (raw / "SOURCES.md").write_text("# Verified dataset downloads\n\n" + "\n".join(
        f"- {n}: https://doi.org/{v['doi']}; license {v['license']}; repository checksum "
        f"`{v['repository_checksum']}`; SHA256 `{v['sha256']}`" for n, v in manifest.items()), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=RAW)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--sources", nargs="+", choices=list(SOURCES), default=["dims"])
    args = parser.parse_args()
    print(json.dumps(fetch(args.raw, args.offline, args.sources), indent=2))
