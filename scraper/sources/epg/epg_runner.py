"""
epg_runner.py
Clones iptv-org/epg and grabs XMLTV data site by site.
Correct usage: npm run grab --- --site=sky.com --output=guide.xml --days=3

Sites we grab from:
  sky.com          — UK: TNT Sports 1-4, Sky Sports Main Event/PL/Football/Action
  canalplus.com    — France/MENA: beIN Sports 1-2, Max 1-10, Canal+ Sport/Foot
  sky.de           — Germany: Sky Sport Bundesliga, DAZN 1-2
  airtelxstream.in — India: Star Sports 1-3, Sony Ten 1-4, Sports18
  astro.com.my     — Malaysia: Astro SuperSport 2-4
  dstv.com         — Africa: SuperSport Premier League/Football/Variety
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

# Sites to grab in priority order. Each produces its own guide XML
# which we then merge into a single guide.xml
SITES = [
    "sky.com",
    "canalplus.com",
    "sky.de",
    "airtelxstream.in",
]


def _run(cmd: list, cwd: str = None, timeout: int = 300) -> tuple[bool, str]:
    """Run a command. Returns (success, stderr)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return False, result.stderr[:1000]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Timed out"
    except Exception as e:
        return False, str(e)


def _ensure_epg_tool() -> bool:
    """Clone and install iptv-org/epg if not already present."""
    node_modules = os.path.join(EPG_TOOL_DIR, "node_modules")
    if os.path.isdir(node_modules):
        logger.info("[epg_runner] EPG tool already installed")
        return True

    logger.info(f"[epg_runner] Cloning iptv-org/epg to {EPG_TOOL_DIR}...")
    os.makedirs(os.path.dirname(EPG_TOOL_DIR), exist_ok=True)

    ok, err = _run(
        ["git", "clone", "--depth=1", EPG_REPO_URL, EPG_TOOL_DIR],
        timeout=180
    )
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


def _merge_guides(guide_files: list, output_xml: str):
    """Merge multiple guide XML files into one."""
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
    logger.info(f"[epg_runner] Merged guide: {len(channel_ids)} channels, {prog_count} programmes → {output_xml}")


def run_epg_grab(channels_xml: str, output_xml: str) -> bool:
    """
    Run iptv-org/epg grab for all target sites.
    Merges results into output_xml.
    Returns True if at least one site succeeded.
    """
    if not _ensure_epg_tool():
        return False

    guide_files = []
    successes = 0

    for site in SITES:
        site_output = os.path.join(EPG_TOOL_DIR, f"guide_{site.replace('.', '_')}.xml")
        logger.info(f"[epg_runner] Grabbing {site}...")

        ok, err = _run(
            ["npm", "run", "grab", "---",
             f"--site={site}",
             f"--output={site_output}",
             "--days=3",
             "--timeout=20000",
             "--maxConnections=1"],
            cwd=EPG_TOOL_DIR,
            timeout=300
        )

        if ok and os.path.isfile(site_output):
            size = os.path.getsize(site_output)
            logger.info(f"[epg_runner] {site}: OK ({size:,} bytes)")
            guide_files.append(site_output)
            successes += 1
        else:
            logger.warning(f"[epg_runner] {site}: failed — {err[:200]}")

    if not guide_files:
        logger.error("[epg_runner] All sites failed — no EPG data")
        return False

    _merge_guides(guide_files, output_xml)
    logger.info(f"[epg_runner] Grab complete: {successes}/{len(SITES)} sites succeeded")
    return True
