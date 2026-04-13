"""
epg_runner.py
Clones iptv-org/epg on first run, then grabs XMLTV data for
all channels defined in epg_channels.xml.

Outputs: guide.xml in the project root
"""

import logging
import os
import subprocess
import shutil

logger = logging.getLogger(__name__)

# Where to clone the epg tool relative to the scraper directory
EPG_TOOL_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "epg_tool")
EPG_TOOL_DIR = os.path.abspath(EPG_TOOL_DIR)
EPG_REPO_URL = "https://github.com/iptv-org/epg.git"


def _run(cmd: list, cwd: str = None, timeout: int = 300) -> bool:
    """Run a shell command, return True on success."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            logger.error(f"[epg_runner] Command failed: {' '.join(cmd)}")
            logger.error(f"[epg_runner] stderr: {result.stderr[:500]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error(f"[epg_runner] Command timed out: {' '.join(cmd)}")
        return False
    except Exception as e:
        logger.error(f"[epg_runner] Command error: {e}")
        return False


def _ensure_epg_tool() -> bool:
    """Clone and install iptv-org/epg if not already present."""
    if os.path.isdir(os.path.join(EPG_TOOL_DIR, "node_modules")):
        logger.info("[epg_runner] EPG tool already installed")
        return True

    logger.info(f"[epg_runner] Cloning iptv-org/epg to {EPG_TOOL_DIR}...")
    os.makedirs(EPG_TOOL_DIR, exist_ok=True)

    # Clone (shallow for speed)
    if not _run(
        ["git", "clone", "--depth=1", EPG_REPO_URL, EPG_TOOL_DIR],
        timeout=120
    ):
        return False

    # Install npm dependencies
    logger.info("[epg_runner] Running npm install...")
    if not _run(["npm", "install"], cwd=EPG_TOOL_DIR, timeout=180):
        return False

    logger.info("[epg_runner] EPG tool installed successfully")
    return True


def run_epg_grab(channels_xml: str, output_xml: str) -> bool:
    """
    Run the iptv-org/epg grab tool for all channels in channels_xml.
    Writes XMLTV output to output_xml.
    Returns True if successful.
    """
    if not os.path.isfile(channels_xml):
        logger.error(f"[epg_runner] channels.xml not found: {channels_xml}")
        return False

    if not _ensure_epg_tool():
        logger.error("[epg_runner] Could not set up EPG tool")
        return False

    logger.info("[epg_runner] Running EPG grab...")

    # iptv-org/epg grab command
    # --channels: path to channels XML
    # --output:   where to write guide.xml
    # --timeout:  ms per channel request
    # --days:     how many days ahead to grab (2 days = sufficient for nightly)
    success = _run(
        [
            "node", "scripts/grab.js",
            "--channels", channels_xml,
            "--output",   output_xml,
            "--timeout",  "30000",
            "--days",     "3",
        ],
        cwd=EPG_TOOL_DIR,
        timeout=600,  # 10 minutes max for full grab
    )

    if success and os.path.isfile(output_xml):
        size = os.path.getsize(output_xml)
        logger.info(f"[epg_runner] guide.xml written ({size:,} bytes)")
        return True
    else:
        logger.warning("[epg_runner] Grab failed or guide.xml not created")
        return False
