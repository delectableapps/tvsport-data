"""
sources/epg/epg_runner.py
==========================
Drives the iptv-org/epg Node.js grab tool from Python,
then parses the resulting guide.xml using epg_xmltv_parser.py.

This is the primary data source for TVsport — replacing most HTML scrapers
with structured EPG data from 4,500+ channels worldwide.

Prerequisites (installed once):
    git clone --depth 1 https://github.com/iptv-org/epg.git epg_tool
    cd epg_tool && npm install

GitHub Actions installs these automatically via setup steps in the workflow.
"""

import os
import subprocess
import logging
import shutil
from pathlib import Path

from sources.epg.epg_xmltv_parser import parse_guide

logger = logging.getLogger(__name__)

# Path to iptv-org/epg clone — set via env var or default
EPG_TOOL_DIR = os.environ.get(
    "EPG_TOOL_DIR",
    os.path.join(os.path.dirname(__file__), "epg_tool")
)

# Our custom channels config
CHANNELS_XML = os.path.join(os.path.dirname(__file__), "epg_channels.xml")

# Output guide file
GUIDE_OUTPUT = os.path.join(os.path.dirname(__file__), "guide.xml")


def _is_tool_available() -> bool:
    """Check if iptv-org/epg Node.js tool is installed."""
    tool_path = Path(EPG_TOOL_DIR)
    package_json = tool_path / "package.json"
    node_modules = tool_path / "node_modules"
    return package_json.exists() and node_modules.exists()


def _install_tool():
    """Clone and install iptv-org/epg if not present."""
    tool_path = Path(EPG_TOOL_DIR)

    if not tool_path.exists():
        logger.info(f"Cloning iptv-org/epg to {EPG_TOOL_DIR}...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/iptv-org/epg.git",
             str(EPG_TOOL_DIR)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone iptv-org/epg: {result.stderr}")
        logger.info("Cloned successfully")
    else:
        logger.info("iptv-org/epg already cloned")

    # Install npm dependencies
    logger.info("Installing npm dependencies...")
    result = subprocess.run(
        ["npm", "install"],
        cwd=EPG_TOOL_DIR,
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"npm install failed: {result.stderr}")
    logger.info("npm install complete")


def grab_epg(days: int = 2, timeout_seconds: int = 600) -> bool:
    """
    Run the iptv-org/epg grab tool with our custom channels config.
    Downloads EPG data for all channels in epg_channels.xml.

    Args:
        days: Number of days to fetch (1-7, default 2 for nightly runs)
        timeout_seconds: Max time to wait for grab to complete

    Returns True if successful, False if failed.
    """
    if not _is_tool_available():
        logger.info("iptv-org/epg not installed — installing now...")
        try:
            _install_tool()
        except Exception as e:
            logger.error(f"Failed to install EPG tool: {e}")
            return False

    logger.info(f"Running EPG grab for {days} days...")
    logger.info(f"  Channels: {CHANNELS_XML}")
    logger.info(f"  Output:   {GUIDE_OUTPUT}")

    cmd = [
        "npm", "run", "grab", "--",
        "--channels", CHANNELS_XML,
        "--output", GUIDE_OUTPUT,
        "--days", str(days),
        "--timeout", "30000",  # 30s per channel request
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=EPG_TOOL_DIR,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )

        if result.returncode != 0:
            logger.error(f"EPG grab failed (exit {result.returncode})")
            logger.error(f"stderr: {result.stderr[-2000:]}")
            return False

        # Check output file exists and has content
        if not os.path.exists(GUIDE_OUTPUT):
            logger.error("guide.xml not created — grab may have failed silently")
            return False

        file_size = os.path.getsize(GUIDE_OUTPUT)
        if file_size < 1000:
            logger.warning(f"guide.xml is very small ({file_size} bytes) — may be empty")
            return False

        logger.info(f"EPG grab complete. guide.xml: {file_size:,} bytes")

        # Log summary from stdout
        for line in result.stdout.split("\n"):
            if any(kw in line.lower() for kw in ["error", "warning", "total", "channels"]):
                logger.info(f"  EPG: {line.strip()}")

        return True

    except subprocess.TimeoutExpired:
        logger.error(f"EPG grab timed out after {timeout_seconds}s")
        return False
    except FileNotFoundError:
        logger.error("npm not found — Node.js may not be installed")
        return False
    except Exception as e:
        logger.error(f"EPG grab error: {e}")
        return False


def get_epg_fixtures(days_ahead: int = 30) -> dict:
    """
    Main entry point. Runs EPG grab then parses results.

    Returns dict of fixture_key → fixture data with broadcaster list.
    Falls back to existing guide.xml if grab fails.
    """
    # Try to grab fresh data
    grab_days = min(days_ahead, 7)  # EPG tools typically support max 7 days
    success = grab_epg(days=grab_days)

    if not success:
        # Check if we have a cached guide.xml from a previous run
        if os.path.exists(GUIDE_OUTPUT):
            logger.warning("EPG grab failed — using cached guide.xml")
        else:
            logger.error("EPG grab failed and no cached guide.xml — returning empty")
            return {}

    # Parse the guide.xml
    logger.info("Parsing guide.xml...")
    fixtures = parse_guide(GUIDE_OUTPUT, days_ahead=days_ahead)
    logger.info(f"EPG yielded {len(fixtures)} fixtures")
    return fixtures


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    )

    print("Testing EPG runner...")
    fixtures = get_epg_fixtures(days_ahead=7)

    if fixtures:
        print(f"\n✅ EPG working — {len(fixtures)} fixtures found\n")
        for key, fx in sorted(fixtures.items(), key=lambda x: x[1]["date"]):
            print(f"  {fx['date']} {fx['kickoff_utc'][11:16]}  "
                  f"{fx['home']} v {fx['away']}  [{fx['competition']}]")
            for b in fx["broadcasters"][:2]:
                print(f"    → {b['country']}: {b['broadcaster']} — {b['channels']}")
    else:
        print("❌ No fixtures found — check EPG tool installation")
