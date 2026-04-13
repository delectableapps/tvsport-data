"""
epg_runner.py
Clones iptv-org/epg and grabs XMLTV data site by site.
Uses npx tsx directly to avoid npm arg-passing issues.
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

SITES = [
    "sky.com",
    "canalplus.com",
    "sky.de",
    "airtelxstream.in",
]


def _run(cmd: list, cwd: str = None, timeout: int = 300) -> tuple:
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stderr[:1000]
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as e:
        return False, str(e)


def _ensure_epg_tool() -> bool:
    node_modules = os.path.join(EPG_TOOL_DIR, "node_modules")
    if os.path.isdir(node_modules):
        logger.info("[epg_runner] EPG tool already installed")
        return True

    logger.info(f"[epg_runner] Cloning iptv-org/epg...")
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


def _get_grab_script() -> str | None:
    """Find the grab script path within the cloned repo."""
    candidates = [
        os.path.join(EPG_TOOL_DIR, "scripts", "commands", "epg", "grab.ts"),
        os.path.join(EPG_TOOL_DIR, "scripts", "grab.ts"),
        os.path.join(EPG_TOOL_DIR, "scripts", "grab.js"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _merge_guides(guide_files: list, output_xml: str):
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
    logger.info(f"[epg_runner] Merged: {len(channel_ids)} channels, {prog_count} programmes → {output_xml}")


def run_epg_grab(channels_xml: str, output_xml: str) -> bool:
    if not _ensure_epg_tool():
        return False

    # Find the grab script
    grab_script = _get_grab_script()
    if not grab_script:
        logger.error(f"[epg_runner] Could not find grab script in {EPG_TOOL_DIR}")
        # Log what's actually in the scripts directory
        scripts_dir = os.path.join(EPG_TOOL_DIR, "scripts")
        if os.path.isdir(scripts_dir):
            for root, dirs, files in os.walk(scripts_dir):
                for f in files:
                    logger.info(f"[epg_runner] Found script: {os.path.join(root, f)}")
        return False

    logger.info(f"[epg_runner] Using grab script: {grab_script}")
    guide_files = []
    successes = 0

    for site in SITES:
        site_output = os.path.join(EPG_TOOL_DIR, f"guide_{site.replace('.', '_')}.xml")
        logger.info(f"[epg_runner] Grabbing {site}...")

        # Call npx tsx directly, bypassing npm run
        cmd = [
            "npx", "tsx", grab_script,
            f"--site={site}",
            f"--output={site_output}",
            "--days=3",
            "--timeout=20000",
            "--maxConnections=1",
        ]

        ok, err = _run(cmd, cwd=EPG_TOOL_DIR, timeout=300)

        if ok and os.path.isfile(site_output):
            size = os.path.getsize(site_output)
            logger.info(f"[epg_runner] {site}: OK ({size:,} bytes)")
            guide_files.append(site_output)
            successes += 1
        else:
            logger.warning(f"[epg_runner] {site}: failed — {err[:300]}")

    if not guide_files:
        logger.error("[epg_runner] All sites failed — no EPG data")
        return False

    _merge_guides(guide_files, output_xml)
    logger.info(f"[epg_runner] Complete: {successes}/{len(SITES)} sites succeeded")
    return True
