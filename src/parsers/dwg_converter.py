"""DWG → DXF conversion using the ODA File Converter.

The ODA File Converter is a free command-line tool from the Open Design
Alliance.  It must be installed separately and its path configured via the
``ODA_CONVERTER_PATH`` environment variable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_ODA_PATH = r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"


class DWGConversionError(Exception):
    pass


class DWGConverter:
    """Convert .dwg files to .dxf using the ODA File Converter."""

    def __init__(self, oda_path: str | None = None) -> None:
        self._oda_path = oda_path or os.environ.get("ODA_CONVERTER_PATH", _DEFAULT_ODA_PATH)

    def convert(self, dwg_path: str | Path) -> Path:
        """Convert *dwg_path* to DXF, returning the path to the new .dxf file.

        Raises ``DWGConversionError`` if conversion fails.
        """
        dwg_path = Path(dwg_path)
        if not dwg_path.exists():
            raise FileNotFoundError(f"DWG file not found: {dwg_path}")

        if not Path(self._oda_path).exists():
            raise DWGConversionError(
                f"ODA File Converter not found at {self._oda_path}. "
                "Install from https://www.opendesign.com/guestfiles/oda_file_converter "
                "and set ODA_CONVERTER_PATH."
            )

        with tempfile.TemporaryDirectory() as tmp_out:
            tmp_in = tempfile.mkdtemp()
            try:
                shutil.copy2(dwg_path, tmp_in)
                cmd = [
                    self._oda_path,
                    tmp_in,
                    tmp_out,
                    "ACAD2018",  # output version
                    "DXF",       # output format
                    "0",         # recurse: no
                    "1",         # audit: yes
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120,
                )
                if result.returncode != 0:
                    raise DWGConversionError(
                        f"ODA conversion failed (code {result.returncode}): {result.stderr}"
                    )

                dxf_files = list(Path(tmp_out).glob("*.dxf"))
                if not dxf_files:
                    raise DWGConversionError("ODA conversion produced no DXF output")

                output = dwg_path.with_suffix(".dxf")
                shutil.move(str(dxf_files[0]), str(output))
                logger.info("dwg_converted", input=str(dwg_path), output=str(output))
                return output
            finally:
                shutil.rmtree(tmp_in, ignore_errors=True)
