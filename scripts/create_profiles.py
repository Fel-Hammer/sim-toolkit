import subprocess
import json
import os
import re
import sys
import configparser
from typing import Dict, List, Any
import logging

logging.basicConfig(level=logging.INFO)

# Configuration constants
CRAFTED_ITEM_IDS = {
    "wrists": 219334,
    "feet": 219327,
    "waist": 219331,
    "finger1": 435384,
    "finger2": 435384,
    "neck": 435385,
    "off_hand": 222441,  # We don't replace the off_hand item ID for weapon embellishments
}

DEFAULT_SLOTS = ["wrist", "off_hand"]

INVENTORY_TYPE_TO_SLOT = {
    0: "non_equipable",
    1: "head",
    2: "neck",
    3: "shoulder",
    4: "shirt",
    5: "chest",
    6: "waist",
    7: "legs",
    8: "feet",
    9: "wrists",
    10: "hands",
    11: "finger",
    12: "trinket",
    13: "main_hand",
    14: "shield",
    15: "ranged",
    16: "back",
    17: "main_hand",
    18: "bag",
    19: "tabard",
    20: "robe",
    21: "main_hand",
    22: "off_hand",
    23: "off_hand",
    24: "ammo",
    25: "thrown",
    26: "ranged_right",
    27: "quiver",
    28: "relic",
}


def load_json(file_name: str) -> List[Dict[str, Any]]:
    with open(file_name, "r") as f:
        return json.load(f)


def load_gear(file_name: str) -> Dict[str, str]:
    gear = {}
    with open(file_name, "r") as f:
        for line in f:
            if "=" in line:
                slot, item = line.strip().split("=", 1)
                gear[slot] = item
    return gear


def clean_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    cleaned = re.sub(r"quality_?(\d*)", r"_\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"__+", "_", cleaned)
    return cleaned.rstrip("_").lower()


def generate_trinket_profilesets(trinkets: List[Dict[str, Any]]) -> List[str]:
    profilesets = []
    for trinket in trinkets:
        if trinket["inventoryType"] == 12 and "template" not in trinket["name"].lower():
            name = clean_name(trinket["name"])
            item_id = trinket["id"]
            item_levels = [593, 606, 619, 626, 639]

            if "Darkmoon Deck" in trinket["name"]:
                item_levels = [577]
            elif trinket["name"] == "Bronzebeard Family Compass":
                item_levels = [597, 610, 623, 630, 643]

            for ilevel in item_levels:
                profileset = f'profileset."{name}_{ilevel}"=trinket1=\nprofileset."{name}_{ilevel}"+=trinket2={name},id={item_id},ilevel={ilevel}'
                profilesets.append(profileset)

    profilesets.append(
        'profileset."No_Trinkets"=trinket1=\nprofileset."No_Trinkets"+=trinket2='
    )
    return profilesets


def generate_enchant_profilesets(
    enchants: List[Dict[str, Any]], gear: Dict[str, str]
) -> Dict[str, List[str]]:
    profilesets = {"Legs": [], "Rings": [], "Weapons": [], "Chest": [], "Other": []}
    slots = {
        "Weapon Enchantments": ("Weapons", "main_hand"),
        "Ring Enchantments": ("Rings", "finger1"),
        "Chest Enchantments": ("Chest", "chest"),
        "Cloak Enchantments": ("Other", "back"),
        "Wrist Enchantments": ("Other", "wrist"),
        "Hand Enchantments": ("Other", "hands"),
        "Foot Enchantments": ("Other", "feet"),
    }

    for enchant in enchants:
        if "template" in enchant.get("displayName", "").lower():
            continue

        category_name = enchant.get("categoryName", "")
        name = enchant.get("displayName", f'Enchant_{enchant.get("id", "Unknown")}')
        profileset_name = clean_name(name)
        enchant_id = enchant.get("id")

        if not enchant_id:
            continue

        if category_name in slots:
            slot_category, gear_slot = slots[category_name]
            if gear_slot in gear:
                if category_name == "Ring Enchantments":
                    for finger in ["finger1", "finger2"]:
                        profileset = f'profileset."{profileset_name}"+={finger}={gear[finger]},enchant_id={enchant_id}'
                        profilesets[slot_category].append(profileset)
                elif category_name == "Weapon Enchantments":
                    profileset = f'profileset."{profileset_name}"+=main_hand={gear[gear_slot]},enchant_id={enchant_id}'
                    profilesets[slot_category].append(profileset)
                    if "off_hand" in gear:
                        profileset = f'profileset."{profileset_name}"+=off_hand={gear["off_hand"]},enchant_id={enchant_id}'
                        profilesets[slot_category].append(profileset)
                else:
                    profileset = f'profileset."{profileset_name}"+={gear_slot}={gear[gear_slot]},enchant_id={enchant_id}'
                    profilesets[slot_category].append(profileset)
        elif "Armor Kit" in enchant.get("itemName", "") and "legs" in gear:
            profileset = f'profileset."Legs_{profileset_name}"+=legs={gear["legs"]},enchant_id={enchant_id}'
            profilesets["Legs"].append(profileset)

    return profilesets


def generate_gem_profilesets(
    gems: List[Dict[str, Any]], gear: Dict[str, str]
) -> List[str]:
    profilesets = []
    for gem in gems:
        if (
            gem.get("slot") == "socket"
            and "template" not in gem.get("itemName", "").lower()
        ):
            name = gem.get("itemName", f'Gem_{gem.get("id", "Unknown")}')
            profileset_name = clean_name(name)
            gem_id = gem.get("itemId")

            if not gem_id:
                continue

            profilesets.extend(
                [
                    f'profileset."{profileset_name}"+=finger1={gear["finger1"]},gem_id={gem_id}',
                    f'profileset."{profileset_name}"+=finger2={gear["finger2"]},gem_id=',
                ]
            )

    return profilesets


def generate_consumable_profilesets(consumables: List[Dict[str, Any]]) -> List[str]:
    profilesets = []
    for consumable in consumables:
        name = clean_name(consumable["name"])
        item_id = consumable["itemId"]
        if "potion" in consumable["value"]:
            profileset = f'profileset."{name}"=potion={item_id}'
        elif "flask" in consumable["value"]:
            profileset = f'profileset."{name}"=flask={item_id}'
        else:
            continue
        profilesets.append(profileset)

    profilesets.append(
        'profileset."no_consumables"=potion=\nprofileset."no_consumables"+=flask='
    )
    return profilesets


def write_profilesets(profilesets: List[str], filename: str) -> None:
    unique_profilesets = {}
    for profileset in profilesets:
        name = profileset.split('"')[1]
        if name not in unique_profilesets:
            unique_profilesets[name] = []
        unique_profilesets[name].append(profileset)

    with open(filename, "w") as f:
        for profileset_lines in unique_profilesets.values():
            f.write("\n".join(profileset_lines) + "\n\n")

    print(f"Generated {len(unique_profilesets)} unique profilesets in {filename}")


def write_enchant_profilesets(
    profilesets: Dict[str, List[str]], base_path: str
) -> None:
    for category, profiles in profilesets.items():
        if profiles:
            filename = f"{base_path}/enchant_profilesets_{category.lower()}.simc"
            write_profilesets(profiles, filename)


def is_full_item_embellishment(emb):
    return "id" in emb and "bonusLists" in emb


def get_valid_slots_for_embellishment(emb):
    if is_full_item_embellishment(emb):
        if "weapon" in emb.get("eligible_slots", []) or emb["name"].startswith(
            "Darkmoon Sigil"
        ):
            return ["off_hand"]
        return [INVENTORY_TYPE_TO_SLOT.get(emb.get("inventoryType"))]
    valid_slots = []
    for slot in emb.get("eligible_slots", []):
        if slot == "weapon":
            valid_slots.append("off_hand")
        elif slot == "finger":
            valid_slots.extend(["finger1", "finger2"])
        elif slot in CRAFTED_ITEM_IDS:
            valid_slots.append(slot)
    return valid_slots


def apply_embellishment(emb, gear, exclude_slot=None):
    valid_slots = get_valid_slots_for_embellishment(emb)

    if is_full_item_embellishment(emb):
        slot = valid_slots[0] if valid_slots else None
    else:
        slot = next((s for s in valid_slots if s in gear and s != exclude_slot), None)

    if not slot:
        reason = f"No valid slot found. Valid slots: {valid_slots}"
    elif slot not in gear:
        reason = f"Slot {slot} not found in gear"
    elif exclude_slot == slot:
        reason = f"Slot {slot} is excluded (already used by another embellishment)"
    else:
        reason = None

    if reason:
        logging.warning(
            f"No valid slots available for {emb['name']}. Reason: {reason}."
        )
        return None, None

    item = gear[slot]
    if is_full_item_embellishment(emb):
        new_item = f"{emb['id']},bonus_id={'/'.join(map(str, emb['bonusLists']))}"
        # Preserve enchant_id and gem_id
        for part in item.split(","):
            if part.startswith("enchant_id=") or part.startswith("gem_id="):
                new_item += f",{part}"
    else:
        bonus_ids = "/".join(map(str, emb.get("craftingBonusIds", [])))
        new_item = f"{CRAFTED_ITEM_IDS[slot]},bonus_id={bonus_ids}"
        # Preserve other properties
        for part in item.split(","):
            if not part.startswith("id=") and not part.startswith("bonus_id="):
                new_item += f",{part}"

    gear[slot] = new_item
    return gear, slot


def remove_bonus_ids(item):
    parts = item.split(",")
    return ",".join([part for part in parts if not part.startswith("bonus_id=")])


def generate_embellishment_pair_profileset(emb1, emb2, gear):
    gear_copy = gear.copy()

    # Try to apply emb1 first
    gear_copy, slot1 = apply_embellishment(emb1, gear_copy)
    if not gear_copy:
        return None

    # Try to apply emb2
    gear_copy, slot2 = apply_embellishment(emb2, gear_copy, exclude_slot=slot1)

    # If emb2 failed, try to apply emb1 to a different slot
    if not gear_copy:
        gear_copy = gear.copy()
        gear_copy, slot2 = apply_embellishment(emb2, gear_copy)
        if not gear_copy:
            return None
        gear_copy, slot1 = apply_embellishment(emb1, gear_copy, exclude_slot=slot2)
        if not gear_copy or slot1 == slot2:
            return None

    name1, name2 = clean_name(emb1["name"]), clean_name(emb2["name"])
    profileset_name = f'"{name1}_and_{name2}"'

    profilesets = [
        f"profileset.{profileset_name}={slot1}={gear_copy[slot1]}",
        f"profileset.{profileset_name}+={slot2}={gear_copy[slot2]}",
    ]

    # Remove bonus_ids from unused default slots
    for default_slot in DEFAULT_SLOTS:
        if default_slot not in [slot1, slot2] and default_slot in gear_copy:
            gear_copy[default_slot] = remove_bonus_ids(gear_copy[default_slot])
            profilesets.append(
                f"profileset.{profileset_name}+={default_slot}={gear_copy[default_slot]}"
            )

    return profilesets


def generate_embellishment_profilesets(embellishments, gear):
    profilesets = []
    for i, emb1 in enumerate(embellishments):
        for j, emb2 in enumerate(embellishments[i:], i):
            profileset_pair = generate_embellishment_pair_profileset(emb1, emb2, gear)
            if profileset_pair:
                profilesets.extend(profileset_pair)
    return profilesets


def update_item_with_embellishment(item, bonus_ids):
    parts = item.split(",")
    new_parts = []
    for part in parts:
        if part.startswith("bonus_id="):
            existing_ids = part.split("=")[1].split("/")
            all_ids = list(set(existing_ids + bonus_ids.split("/")))
            new_parts.append(f"bonus_id={'/'.join(all_ids)}")
        else:
            new_parts.append(part)

    if "crafted_stats=" not in item:
        new_parts.append("crafted_stats=36/40")
    return ",".join(new_parts)


def clear_embellishment_from_item(item):
    parts = item.split(",")
    new_parts = [part for part in parts if not part.startswith("bonus_id=")]
    return ",".join(new_parts)


def main():
    if len(sys.argv) < 2:
        print("Usage: python create_profiles.py <path_to_config.ini>")
        sys.exit(1)

    config_path = os.path.abspath(sys.argv[1])
    config_dir = os.path.dirname(config_path)

    config = configparser.ConfigParser()
    config.read(config_path)

    apl_folder = config.get("General", "apl_folder")
    apl_folder_full_path = os.path.join(config_dir, apl_folder)

    print(f"Config file: {config_path}")
    print(f"APL folder: {apl_folder_full_path}")

    print("Fetching and filtering items and enchants...")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    filter_script_path = os.path.join(script_dir, "filter_items_enchants.py")
    subprocess.run([sys.executable, filter_script_path], check=True)

    data_dir = os.path.join(config_dir, "data")
    required_files = [
        os.path.join(data_dir, "filtered_items.json"),
        os.path.join(data_dir, "filtered_enchants.json"),
        os.path.join(data_dir, "filtered_consumables.json"),
        os.path.join(data_dir, "filtered_embellishments.json"),
    ]
    if not all(os.path.exists(file) for file in required_files):
        print(
            "Error: Required JSON files not found in the /data folder. Make sure filter_items_enchants.py created these files."
        )
        return

    trinkets = load_json(required_files[0])
    enchants = load_json(required_files[1])
    gems = load_json(required_files[1])
    consumables = load_json(required_files[2])
    embellishments = load_json(required_files[3])

    gear_file_path = os.path.join(apl_folder_full_path, "gear.simc")
    print(f"Looking for gear file at: {gear_file_path}")

    if not os.path.exists(gear_file_path):
        print(f"Error: gear.simc not found at {gear_file_path}")
        print(
            "Please make sure the apl_folder in your config.ini is correct and contains a gear.simc file."
        )
        return

    gear = load_gear(gear_file_path)

    trinket_profilesets = generate_trinket_profilesets(trinkets)
    write_profilesets(
        trinket_profilesets,
        os.path.join(apl_folder_full_path, "trinket_profilesets.simc"),
    )

    enchant_profilesets = generate_enchant_profilesets(enchants, gear)
    write_enchant_profilesets(enchant_profilesets, apl_folder_full_path)

    gem_profilesets = generate_gem_profilesets(gems, gear)
    write_profilesets(
        gem_profilesets, os.path.join(apl_folder_full_path, "gem_profilesets.simc")
    )

    consumable_profilesets = generate_consumable_profilesets(consumables)
    write_profilesets(
        consumable_profilesets,
        os.path.join(apl_folder_full_path, "consumable_profilesets.simc"),
    )

    embellishment_profilesets = generate_embellishment_profilesets(embellishments, gear)
    write_profilesets(
        embellishment_profilesets,
        os.path.join(apl_folder_full_path, "embellishment_profilesets.simc"),
    )


if __name__ == "__main__":
    main()
