"""
epg_runner.py
Uses iptv-org/epg with our custom epg_channels.xml.
Our channels file has only the specific channels we need (~40 channels total)
so grabs complete in reasonable time.
"""

import logging
import os
import subprocess
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

EPG_TOOL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "epg_tool")
)
EPG_REPO_URL = "https://github.com/iptv-org/epg.git"


def _run(cmd, cwd=None, timeout=300):
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stderr[:1000]
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as e:
        return False, str(e)


def _ensure_epg_tool():
    node_modules = os.path.join(EPG_TOOL_DIR, "node_modules")
    if os.path.isdir(node_modules):
        logger.info("[epg_runner] EPG tool already installed")
        return True

    logger.info("[epg_runner] Cloning iptv-org/epg...")
    os.makedirs(os.path.dirname(EPG_TOOL_DIR), exist_ok=True)

    ok, err = _run(["git", "clone", "--depth=1", EPG_REPO_URL, EPG_TOOL_DIR], timeout=180)
    if not ok:
        logger.error(f"[epg_runner] Clone failed: {err}")
        return False

    logger.info("[epg_runner] Running npm install...")
    ok, err = _run(["npm", "install"], cwd=EPG_TOOL_DIR, timeout=300)
    if not ok:
        logger.error(f"[epg_runner] npm install failed: {err}")
        return False

    logger.info("[epg_runner] EPG tool installed successfully")
    return True


def run_epg_grab(channels_xml: str, output_xml: str) -> bool:
    """
    Run iptv-org/epg grab using our custom channels_xml file.
    This file contains only the ~40 channels we care about, so it completes quickly.
    """
    if not os.path.isfile(channels_xml):
        logger.error(f"[epg_runner] channels_xml not found: {channels_xml}")
        return False

    if not _ensure_epg_tool():
        return False

    logger.info(f"[epg_runner] Grabbing EPG using {os.path.basename(channels_xml)}...")

    # Use our epg_channels.xml directly — this is the key fix.
    # Previously was trying to use the bundled sky.com full channels list (1000+ channels).
    # Our file has only ~40 channels so completes in 2-3 minutes.
    ok, err = _run(
        [
            "npm", "run", "grab", "---",
            f"--channels={channels_xml}",
            f"--output={output_xml}",
            "--days=3",
            "--timeout=20000",
            "--maxConnections=1",
        ],
        cwd=EPG_TOOL_DIR,
        timeout=600  # 10 minutes max
    )

    if ok and os.path.isfile(output_xml):
        size = os.path.getsize(output_xml)
        logger.info(f"[epg_runner] guide.xml written ({size:,} bytes)")
        return True
    else:
        logger.warning(f"[epg_runner] Grab failed: {err[:300]}")
        return False
