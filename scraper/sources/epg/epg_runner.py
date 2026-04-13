"""
epg_runner.py
Clones iptv-org/epg and grabs XMLTV data using --channels flag
pointing to the bundled site channel XML files inside the repo.

Correct usage:
  npm run grab --- --channels=sites/sky.com/sky.com.channels.xml --output=guide.xml --days=3
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

# Channel XML files bundled inside the iptv-org/epg repo
# These contain the full channel lists for each site
SITE_CHANNELS = [
    "sites/sky.com/sky.com.channels.xml",
    "sites/canalplus.com/canalplus.com_fr.channels.xml",
    "sites/sky.de/sky.de.channels.xml",
    "sites/airtelxstream.in/airtelxstream.in.channels.xml",
]


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


def _merge_guides(guide_files, output_xml):
    root = ET.Element("tv")
    channel_ids = set()
    prog_count = 0
    for gf in guide_files:
        if not os.path.isfile(gf):
            continue
        try:
            tree = ET.parse(gf)
            for ch in tree.getroot().findall("channel"):
                ch_id = ch.get("id", "")
                if ch_id and ch_id not in channel_ids:
                    channel_ids.add(ch_id)
                    root.append(ch)
            for prog in tree.getroot().findall("programme"):
                root.append(prog)
                prog_count += 1
        except Exception as e:
            logger.warning(f"[epg_runner] Could not parse {gf}: {e}")
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_xml, encoding="utf-8", xml_declaration=True)
    logger.info(f"[epg_runner] Merged: {len(channel_ids)} channels, {prog_count} programmes")


def run_epg_grab(channels_xml, output_xml):
    if not _ensure_epg_tool():
        return False

    guide_files = []
    successes = 0

    for channels_file in SITE_CHANNELS:
        full_path = os.path.join(EPG_TOOL_DIR, channels_file)
        if not os.path.isfile(full_path):
            logger.warning(f"[epg_runner] Channels file not found: {full_path}")
            continue

        site_name = channels_file.split("/")[1]
        site_output = os.path.join(EPG_TOOL_DIR, f"guide_{site_name.replace('.', '_')}.xml")
        logger.info(f"[epg_runner] Grabbing {site_name}...")

        # Use npm run grab --- with --channels flag (confirmed correct syntax)
        cmd = [
            "npm", "run", "grab", "---",
            f"--channels={channels_file}",
            f"--output={site_output}",
            "--days=3",
            "--timeout=20000",
            "--maxConnections=1",
        ]

        ok, err = _run(cmd, cwd=EPG_TOOL_DIR, timeout=300)

        if ok and os.path.isfile(site_output):
            size = os.path.getsize(site_output)
            logger.info(f"[epg_runner] {site_name}: OK ({size:,} bytes)")
            guide_files.append(site_output)
            successes += 1
        else:
            logger.warning(f"[epg_runner] {site_name}: failed — {err[:300]}")

    if not guide_files:
        logger.error("[epg_runner] All sites failed — no EPG data")
        return False

    _merge_guides(guide_files, output_xml)
    logger.info(f"[epg_runner] Complete: {successes}/{len(SITE_CHANNELS)} sites succeeded")
    return True
