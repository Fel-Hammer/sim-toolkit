import subprocess
import json
import os
import re
import sys
import configparser
from typing import Dict, List, Any

import logging

logging.basicConfig(level=logging.INFO)


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
    # Remove special characters and replace spaces with underscores
    cleaned = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    # Replace "quality" with an underscore, but keep the number
    cleaned = re.sub(r"quality_?(\d*)", r"_\1", cleaned, flags=re.IGNORECASE)
    # Remove any double underscores
    cleaned = re.sub(r"__+", "_", cleaned)
    # Remove any trailing underscores
    cleaned = cleaned.rstrip("_")
    return cleaned.lower()


def generate_trinket_profilesets(trinkets: List[Dict[str, Any]]) -> List[str]:
    profilesets = []
    for trinket in trinkets:
        if trinket["inventoryType"] == 12 and "template" not in trinket["name"].lower():
            name = clean_name(trinket["name"])
            gear_name = name.lower()
            item_id = trinket["id"]
            item_levels = [593, 606, 619, 626, 639]

            # Darkmoon Decks only have one ilevel
            if "Darkmoon Deck" in trinket["name"]:
                item_levels = [577]
            # Trinkets with unique ilevels
            elif trinket["name"] == "Bronzebeard Family Compass":
                item_levels = [597, 610, 623, 630, 643]

            for ilevel in item_levels:
                profileset = f'profileset."{name}_{ilevel}"=trinket1=\nprofileset."{name}_{ilevel}"+=trinket2={gear_name},id={item_id},ilevel={ilevel}'
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
            continue  # Skip other types of consumables

        profilesets.append(profileset)

    # Add a profile for no consumables
    profilesets.append(
        'profileset."no_consumables"=potion=\nprofileset."no_consumables"+=flask='
    )

    return profilesets


def write_profilesets(profilesets: List[str], filename: str) -> None:
    unique_profilesets = {}
    for profileset in profilesets:
        name = profileset.split('"')[1]  # Extract the name between quotes
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


inventory_type_to_slot = {
    1: "head",
    3: "shoulder",
    5: "chest",
    6: "waist",
    7: "legs",
    8: "feet",
    9: "wrist",
    10: "hands",
    16: "back",
    20: "chest",
}


def is_full_item_embellishment(embellishment):
    return (
        "profession" in embellishment
        and "optionalCraftingSlots" in embellishment["profession"]
    )


def get_crafted_items(gear):
    return {slot: item for slot, item in gear.items() if "crafted_stats" in item}


def get_unused_crafted_slot(gear, used_slots):
    crafted_slots = [slot for slot, item in gear.items() if "crafted_stats" in item]
    unused_slots = set(crafted_slots) - set(used_slots)
    return unused_slots.pop() if unused_slots else None


def clear_embellishment_from_item(item):
    parts = item.split(",")
    new_parts = []
    for part in parts:
        if not part.startswith("bonus_id="):
            new_parts.append(part)
    return ",".join(new_parts)


def clear_embellishment_bonus_ids(item):
    if "bonus_id=" not in item:
        return item

    parts = item.split("bonus_id=")
    prefix = parts[0]
    bonus_part = parts[1]

    bonus_ids = [
        bid
        for bid in bonus_part.split(",")[0].split("/")
        if int(bid) < 8900 or int(bid) > 9000
    ]

    if bonus_ids:
        new_item = f"{prefix}bonus_id={'/'.join(bonus_ids)}"
        if "," in bonus_part:
            new_item += "," + ",".join(bonus_part.split(",")[1:])
    else:
        new_item = prefix.rstrip(",")
        if "," in bonus_part:
            new_item += "," + ",".join(bonus_part.split(",")[1:])

    return new_item.rstrip(",")


def generate_embellishment_profilesets(
    embellishments: List[Dict[str, Any]], gear: Dict[str, str]
) -> List[str]:
    profilesets = []

    # Clear existing embellishment bonus_ids
    gear = {slot: clear_embellishment_bonus_ids(item) for slot, item in gear.items()}

    crafted_items = get_crafted_items(gear)

    for i, emb1 in enumerate(embellishments):
        for j, emb2 in enumerate(embellishments[i:]):  # Allow same embellishment
            if i == j and is_full_item_embellishment(emb1):
                continue  # Skip if it's the same full-item embellishment
            profileset_pair = generate_embellishment_pair_profileset(
                emb1, emb2, gear, crafted_items
            )
            if profileset_pair:
                profilesets.extend(profileset_pair)

    return profilesets


def generate_embellishment_pair_profileset(emb1, emb2, gear, crafted_items):
    name1 = clean_name(emb1.get("name", f'{emb1.get("id", "Unknown")}'))
    name2 = clean_name(emb2.get("name", f'{emb2.get("id", "Unknown")}'))

    gear_copy = gear.copy()

    # Apply first embellishment
    gear_copy, used_slot1 = apply_embellishment(emb1, gear_copy, crafted_items)
    if not gear_copy:
        return None

    # Apply second embellishment, excluding the slot used by the first
    gear_copy, used_slot2 = apply_embellishment(
        emb2, gear_copy, crafted_items, exclude_slot=used_slot1
    )
    if not gear_copy or used_slot1 == used_slot2:
        return None

    # Generate profileset strings
    profileset_name = f'"{name1}_and_{name2}"'
    profileset1 = f"profileset.{profileset_name}={used_slot1}={gear_copy[used_slot1]}"
    profileset2 = f"profileset.{profileset_name}+={used_slot2}={gear_copy[used_slot2]}"

    # Handle unused crafted slot
    unused_slot = get_unused_crafted_slot(gear, [used_slot1, used_slot2])
    if unused_slot:
        cleared_item = clear_embellishment_from_item(gear[unused_slot])
        profileset3 = f"profileset.{profileset_name}+={unused_slot}={cleared_item}"
        return [profileset1, profileset2, profileset3]

    return [profileset1, profileset2]


def apply_embellishment(
    emb, gear, crafted_items, specific_slot=None, exclude_slot=None
):
    if is_full_item_embellishment(emb):
        slot = specific_slot or inventory_type_to_slot.get(
            emb.get("inventoryType"), None
        )
        if not slot or slot == exclude_slot:
            return None, None
        bonus_ids = "/".join(map(str, emb.get("bonusLists", [])))
        new_item = f"{emb['id']},bonus_id={bonus_ids}"
        gear[slot] = new_item
        return gear, slot
    else:
        bonus_ids = "/".join(map(str, emb.get("craftingBonusIds", [])))
        available_slots = [s for s in crafted_items.keys() if s != exclude_slot]
        if specific_slot and specific_slot in available_slots:
            slot = specific_slot
        elif "off_hand" in available_slots:
            slot = "off_hand"
        elif available_slots:
            slot = available_slots[0]
        else:
            return None, None

        item = gear[slot]
        # Preserve the original item ID
        original_id = re.search(r"id=(\d+)", item)
        if original_id:
            original_id = original_id.group(1)
        else:
            return None, None  # If we can't find the original ID, we can't proceed

        # Add or update the bonus_id
        if "bonus_id=" in item:
            new_item = re.sub(r"bonus_id=[\d/]+", f"bonus_id={bonus_ids}", item)
        else:
            new_item = f"{item},bonus_id={bonus_ids}"

        new_item = re.sub(r",crafted_stats=\d+\/\d+", "", new_item)
        new_item += ",crafted_stats=36/40"
        gear[slot] = new_item
        return gear, slot


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

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Run the filter_items_enchants.py script with the full path
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
