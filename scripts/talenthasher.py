import json
import sys
import subprocess
import re
import argparse
import pickle
import os
import time
import tempfile
import fcntl
import requests
from datetime import datetime, timedelta
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get the directory of the current script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Get the root directory (parent of the script directory)
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# Configuration constants
TALENTS_URL = "https://www.raidbots.com/static/data/beta/talents.json"
DATA_DIR = os.path.join(ROOT_DIR, "data")
TALENTS_CACHE_FILE = os.path.join(DATA_DIR, "talents_cache.json")
TALENTS_CACHE_LOCK = os.path.join(SCRIPT_DIR, "talents_cache.lock")
CACHE_FILE = os.path.join(SCRIPT_DIR, "talent_cache.pkl")
LOCK_FILE = os.path.join(SCRIPT_DIR, "talent_cache.lock")

# Ensure the data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Configuration constants
SPEC_NAMES = ["Vengeance", "Havoc"]
SIMC_PATH = "../simc/engine/"
MAX_CACHE_AGE = 3600  # 1 hour in seconds

debug = False

# Specific node IDs for different specs and hero choices
HERO_TREE_SELECTOR_NODES = {"vengeance": 99823, "havoc": 99824}

HERO_SPEC_INDEX = {"aldrachi reaver": 0, "felscarred": 1}

HERO_SELECTION_ENTRIES = [123329, 123330]

# Compile regex patterns once for efficiency
ENTRY_PATTERN = re.compile(r"Entry\s+:\s+(\d+)")
NODE_PATTERN = re.compile(r"Node\s+:\s+(\d+)")

# Talent hash generation transliterated from simc implementation
base64_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
# hardcoded values from Interface/AddOns/Blizzard_PlayerSpells/ClassTalents/Blizzard_ClassTalentImportExport.lua
LOADOUT_SERIALIZATION_VERSION = 2
version_bits = 8  # serialization version
spec_bits = 16  # specialization id
tree_bits = 128  # C_Traits.GetTreeHash(), optionally can be 0-filled
rank_bits = 6  # ranks purchased if node is partially filled
choice_bits = 2  # choice index, 0-based
byte_size = (
    6  # hardcoded value from Interface/AddOns/Blizzard_SharedXMLBase/ExportUtil.lua
)

head = 0
byte = 0
export_str = ""

node_names = {}
talent_data = None
force_new_applied = False


def filter_demon_hunter_specs(data):
    """Filter the talent data to include Vengeance and Havoc Demon Hunter."""
    return [
        tree
        for tree in data
        if tree.get("className") == "Demon Hunter"
        and tree.get("classId") == 12
        and tree.get("specName") in SPEC_NAMES
    ]


def acquire_lock(lock_file):
    lock = open(lock_file, "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock
    except IOError:
        return None


def release_lock(lock):
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()


def fetch_talents_json(force_new=False):
    lock = acquire_lock(TALENTS_CACHE_LOCK)
    if not lock:
        print("Unable to acquire lock. Another process might be updating the cache.")
        return load_talent_data()

    try:
        if force_new and os.path.exists(TALENTS_CACHE_FILE):
            os.remove(TALENTS_CACHE_FILE)
            print("Removed existing talents cache due to force_new=True")

        if os.path.exists(TALENTS_CACHE_FILE) and not force_new:
            print("Using cached talents.json")
            with open(TALENTS_CACHE_FILE, "r") as f:
                return json.load(f)

        print("Fetching new talents.json")
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        response = requests.get(TALENTS_URL, headers=headers)
        response.raise_for_status()

        # Filter the data for Demon Hunter specs
        filtered_data = filter_demon_hunter_specs(response.json())

        with open(TALENTS_CACHE_FILE, "w") as f:
            json.dump(filtered_data, f)

        print("Successfully fetched, filtered, and cached new talents.json")
        return filtered_data
    except Exception as e:
        print(f"Error fetching talents.json: {e}")
        if os.path.exists(TALENTS_CACHE_FILE):
            print("Using existing cached talents.json")
            with open(TALENTS_CACHE_FILE, "r") as f:
                return json.load(f)
        else:
            raise
    finally:
        if lock:
            release_lock(lock)


def generate_traits_hash(tree, nodes, hero_spec, spec_name):
    global head, byte, export_str

    head = 0
    byte = 0

    def put_bit(bits, value):
        global head, byte, export_str
        for i in range(0, bits):
            bit = head % byte_size
            head += 1
            byte += ((value >> min(i, sys.getsizeof(value) * 8 - 1)) & 0b1) << bit
            print_debug(head, bits, value, byte, base64_char[byte])
            if bit == byte_size - 1:
                print_debug(f"new char: {base64_char[byte]}")
                export_str += base64_char[byte]
                byte = 0

    export_str = ""
    if nodes == []:
        put_bit(1, 0)
        return export_str
    print_debug("version bits")
    put_bit(version_bits, LOADOUT_SERIALIZATION_VERSION)
    print_debug("spec bits")
    put_bit(spec_bits, tree["specId"])
    print_debug("tree bits")
    put_bit(
        tree_bits, 0
    )  # 0-filled to bypass validation, as GetTreeHash() is unavailable externally

    def get_node_from_id(id):
        print_debug(f"id: {id}")
        for node in tree["classNodes"]:
            if node["id"] == id:
                return node
        for node in tree["specNodes"]:
            if node["id"] == id:
                return node
        for node in tree["heroNodes"]:
            if node["id"] == id:
                return node
        for node in tree["subTreeNodes"]:
            if node["id"] == id:
                return node
        return None

    for node_id in tree["fullNodeOrder"]:
        print_debug(export_str)
        node = get_node_from_id(node_id)
        name = nodes.get(node_id, {}).get("name", "no_name")
        if node is None:
            put_bit(1, 0)
            continue
        rank = 0
        index = 0
        is_choice = node["type"] == "choice" or node["type"] == "subtree"

        entries = node["entries"]
        for i in range(0, len(entries)):
            _node = nodes.get(node["id"], {})
            entry_id = entries[i].get("id")
            if entry_id and entry_id == _node.get("entry_id"):
                rank = _node.get("rank", 0)
                index = i
                break

            if node_id == HERO_TREE_SELECTOR_NODES[spec_name.lower()]:
                rank = 1
                index = HERO_SPEC_INDEX[hero_spec]

        HERO_TREE_FREE_NODES = [94917, 94915]
        if rank or node_id in HERO_TREE_FREE_NODES:
            print_debug("node selected")
            put_bit(1, 1)
        else:
            print_debug("node not selected")
            put_bit(1, 0)
            continue

        if not node.get("freeNode"):
            print_debug("node purchased")
            put_bit(1, 1)
        else:
            print_debug("node is free")
            put_bit(1, 0)
            continue

        if rank == node.get("maxRanks", 1):
            print_debug("node max rank")
            put_bit(1, 0)
        else:
            print_debug("node partial rank")
            put_bit(1, 1)
            put_bit(rank_bits, rank)

        if is_choice:
            print_debug("is choice node")
            put_bit(1, 1)
            put_bit(choice_bits, index)
        else:
            print_debug("not choice node")
            put_bit(1, 0)

    if head % byte_size:
        export_str += base64_char[byte]

    return export_str


def print_debug(*args):
    if debug:
        print(*args)


@lru_cache(maxsize=None)
def load_talent_data():
    return fetch_talents_json()


def load_cache():
    lock = acquire_lock(LOCK_FILE)
    try:
        if os.path.exists(CACHE_FILE):
            if time.time() - os.path.getmtime(CACHE_FILE) <= MAX_CACHE_AGE:
                with open(CACHE_FILE, "rb") as f:
                    return pickle.load(f)
        return {}
    except Exception:
        return {}
    finally:
        if lock:
            release_lock(lock)


def save_cache(cache):
    lock = acquire_lock(LOCK_FILE)
    if not lock:
        return

    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as temp_file:
            pickle.dump(cache, temp_file)
        os.replace(temp_file.name, CACHE_FILE)
    except Exception:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
    finally:
        release_lock(lock)


def fetch_talent_data(name):
    # Fetch talent data from SimC for a given talent name
    data = subprocess.run(
        [SIMC_PATH + "simc", f"spell_query=talent.name={name}"],
        stdout=subprocess.PIPE,
        text=True,
    )
    entry_id = ENTRY_PATTERN.search(data.stdout).group(1)
    node_id = NODE_PATTERN.search(data.stdout).group(1)
    return {"entry_id": int(entry_id), "node_id": int(node_id)}


def process_talent(s, cache):
    # Process a single talent string, using the cache if available
    name, rank = s.split(":")
    if name not in cache:
        cache[name] = fetch_talent_data(name)
    talent_data = cache[name]
    return talent_data["node_id"], {
        "entry_id": talent_data["entry_id"],
        "rank": int(rank),
        "name": name,
    }


def determine_hero_spec(hero_talent_string, spec_name):
    hero_talent_string = hero_talent_string.lower()
    spec_name = spec_name.lower()

    if spec_name == "vengeance":
        if "demonsurge:1" in hero_talent_string:
            return "felscarred"
        elif "art_of_the_glaive:1" in hero_talent_string:
            return "aldrachi reaver"
    elif spec_name == "havoc":
        if "demonsurge:1" in hero_talent_string:
            return "felscarred"
        elif "art_of_the_glaive:1" in hero_talent_string:
            return "aldrachi reaver"
    raise ValueError(
        f"Unable to determine HERO_SPEC for {spec_name} from hero_talent_string"
    )


def initialize_talent_data(force_new=False):
    global talent_data, force_new_applied
    if talent_data is None or (force_new and not force_new_applied):
        talent_data = fetch_talents_json(force_new=force_new)
        force_new_applied = True
    return talent_data


# Initialize talent data when the module is imported
initialize_talent_data()


def generate_talent_hash(
    hero_talent_string,
    class_talent_string,
    spec_talent_string,
    spec_name,
    clear_cache=False,
    force_new=False,
):
    global talent_data

    initialize_talent_data(force_new=force_new)

    if clear_cache:
        lock = acquire_lock(LOCK_FILE)
        if lock:
            try:
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
            finally:
                release_lock(lock)

    cache = load_cache()
    talent_string = f"{class_talent_string}/{spec_talent_string}/{hero_talent_string}"
    node_strs = talent_string.split("/")

    # Process talents concurrently for improved performance
    with ThreadPoolExecutor() as executor:
        future_to_talent = {
            executor.submit(process_talent, s, cache): s for s in node_strs
        }
        nodes = dict(future.result() for future in as_completed(future_to_talent))

    save_cache(cache)

    hero_spec = determine_hero_spec(hero_talent_string, spec_name)

    spec_name = spec_name.capitalize()  # Ensure first letter is capitalized
    for tree in talent_data:
        if tree["specName"].lower() == spec_name.lower():
            return generate_traits_hash(tree, nodes, hero_spec, spec_name)

    raise ValueError(f"Spec {spec_name} not found in talent data")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate talent hash")
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the talent cache before running",
    )
    parser.add_argument("--class-talents", required=True, help="Class talent string")
    parser.add_argument("--spec-talents", required=True, help="Spec talent string")
    parser.add_argument("--hero-talents", required=True, help="Hero talent string")
    parser.add_argument(
        "--force-new",
        action="store_true",
        help="Force fetching a new talents.json file",
    )
    parser.add_argument(
        "--spec", required=True, choices=SPEC_NAMES, help="Demon Hunter specialization"
    )
    args = parser.parse_args()

    # Initialize talent data once
    initialize_talent_data(force_new=args.force_new)

    result = generate_talent_hash(
        args.hero_talents,
        args.class_talents,
        args.spec_talents,
        args.spec,
        clear_cache=args.clear_cache,
    )
    print(result)
