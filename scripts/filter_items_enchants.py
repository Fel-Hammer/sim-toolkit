import json
import re
from collections import defaultdict
import requests
import os


def get_data_file_path(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), "data")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    return os.path.join(data_dir, filename)


def load_data_from_url(url):
    response = requests.get(url)
    response.raise_for_status()  # This will raise an exception for HTTP errors
    return response.json()


def load_items(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def has_agility(item):
    if "stats" in item:
        return any(stat["id"] == 3 for stat in item["stats"])
    return False


def is_valid_trinket_for_demon_hunter(item):
    if (
        item["itemClass"] == 4
        and item["itemSubClass"] == 0
        and item["inventoryType"] == 12
    ):
        if "stats" not in item:
            return True  # Trinkets with no stats are allowed

        has_primary_stat = False
        has_agility = False
        has_stamina = False

        for stat in item["stats"]:
            if stat["id"] in [3, 7]:  # Agility, Stamina
                has_primary_stat = True
                if stat["id"] == 3:  # Agility
                    has_agility = True
                elif stat["id"] == 7:  # Stamina
                    has_stamina = True

        # Allow trinkets with no primary stats, or with Agility or Stamina
        return not has_primary_stat or has_agility or has_stamina

    return True  # Not a trinket, so it passes this check


def is_pvp_item(item):
    # Check for PvP-specific prefixes in the name
    pvp_prefixes = ["Gladiator", "Combatant", "Aspirant", "Veteran"]
    if any(prefix in item["name"] for prefix in pvp_prefixes):
        return True

    # Check for PvP season indicator in the name
    if re.search(r"S\d+", item["name"]):
        return True

    # Check for PvP-specific fields (this might vary depending on the data structure)
    if "pvp" in item and item["pvp"]:
        return True

    return False


def is_usable_by_demon_hunter(item):
    # Demon Hunter class ID
    DH_CLASS_ID = 12
    # Demon Hunter spec IDs
    DH_SPECS = [577, 581]  # Havoc and Vengeance

    # Check if the item is explicitly restricted to certain classes
    if "allowableClasses" in item and DH_CLASS_ID not in item["allowableClasses"]:
        return False

    # Check for leather armor
    if item["itemClass"] == 4 and item["itemSubClass"] == 2:
        return True

    # Check for cloaks (back slot items)
    if (
        item["itemClass"] == 4
        and item["itemSubClass"] == 1
        and item["inventoryType"] == 16
    ):
        return True

    # Check for jewelry and trinkets
    if item["itemClass"] == 4 and item["itemSubClass"] == 0:
        if item["inventoryType"] in [2, 11, 12]:  # Neck, Finger, Trinket
            if item["inventoryType"] == 12:  # Trinket
                return is_valid_trinket_for_demon_hunter(item)
            # If specs are specified, check for Demon Hunter specs
            if "specs" in item:
                return any(spec in DH_SPECS for spec in item["specs"])
            return True  # If no specs are specified, assume it's usable

    # Check for weapons Demon Hunters can use
    if item["itemClass"] == 2:  # Weapon
        usable_weapon_types = [0, 4, 7, 13, 15]  # Axe, Fist, Sword, Warglaive, Dagger
        if item["itemSubClass"] in usable_weapon_types:
            # Exclude all two-handed weapons
            if item["inventoryType"] not in [17, 21]:  # Two-Hand, Main Hand
                return True

    return False


def is_from_specific_dungeon(item):
    specific_dungeon_ids = [
        1271,  # Ara-Kara, City of Echoes
        1274,  # City of Threads
        1269,  # The Stonevault
        1270,  # The Dawnbreaker
        1184,  # Mists of Tirna Scithe
        1182,  # The Necrotic Wake
        1023,  # Siege of Boralus
        71,  # Grim Batol
    ]

    if "sources" in item:
        return any(
            source["instanceId"] in specific_dungeon_ids for source in item["sources"]
        )

    return False


def filter_items(items, current_expansion):
    filtered_items = []
    for item in items:
        if is_usable_by_demon_hunter(item) and not is_pvp_item(item):
            if is_from_specific_dungeon(item):
                # Specific dungeons (current or older): rare (3) and epic (4) quality
                if item["quality"] >= 3:
                    filtered_items.append(item)
            elif item["expansion"] == current_expansion:
                # Current expansion items not from specific dungeons: only epic quality (4)
                if item["quality"] >= 4:
                    filtered_items.append(item)
    return filtered_items


def load_enchants(file_path):
    with open(file_path, "r") as file:
        return json.load(file)


def affects_damage(enchant):
    damage_stats = [
        "agi",
        "agility",
        "stragi",
        "stragiint",
        "mastery",
        "haste",
        "crit",
        "versatility",
        "vers",
        "damage",
        "stamina",
    ]

    # Check stats if present
    if "stats" in enchant:
        for stat in enchant["stats"]:
            if stat["type"].lower() in damage_stats:
                return True

    # Check displayName for damage-related keywords
    damage_keywords = [
        "damage",
        "agility",
        "strength",
        "intellect",
        "primary stat",
        "mastery",
        "haste",
        "crit",
        "versatility",
        "stamina",
    ]
    if any(
        keyword.lower() in enchant["displayName"].lower() for keyword in damage_keywords
    ):
        return True

    # Check for specific enchants that might not have clear stat indicators
    special_damage_enchants = [
        "Accelerated",
        "Deadly",
        "Quick",
        "Accurate",
        "Masterful",
        "Versatile",
        "Primary Stat",
        "All Stats",
        "Instinctive",
        "Illuminated",
        "Armor Kit",
    ]
    if any(keyword in enchant["displayName"] for keyword in special_damage_enchants):
        return True

    # Check categoryName for damage-related categories
    damage_categories = [
        "Chest Enchantments",
        "Weapon Enchantments",
        "Ring Enchantments",
    ]
    if "categoryName" in enchant and enchant["categoryName"] in damage_categories:
        return True

    return False


def is_usable_by_demon_hunter_enchant(enchant):
    # Exclude Runes (Death Knight specific)
    if "categoryName" in enchant and enchant["categoryName"] == "Runes":
        return False

    # Exclude Intellect-only enchants
    if "stats" in enchant:
        stat_types = [stat["type"].lower() for stat in enchant["stats"]]
        if "int" in stat_types or "intellect" in stat_types:
            if not any(
                stat in stat_types
                for stat in ["agi", "agility", "str", "strength", "stragi", "stragiint"]
            ):
                return False

    # Check if the enchant affects damage-related stats
    if not affects_damage(enchant):
        return False

    # Check if the enchant is for items demon hunters can use
    if "equipRequirements" in enchant:
        req = enchant["equipRequirements"]

        # Weapon enchants
        if req["itemClass"] == 2:
            # Check if it's for weapons demon hunters can use
            dh_weapon_mask = 0b1000000000000011110001  # Warglaives, Swords, Axes, Fist Weapons, Daggers
            if req["itemSubClassMask"] & dh_weapon_mask:
                return True

        # Armor enchants
        elif req["itemClass"] == 4:
            # Check if it's for armor types demon hunters can use
            dh_armor_mask = 0b110  # Leather and Cloth
            if req["itemSubClassMask"] & dh_armor_mask:
                return True

    # Gems and other enchants without specific class restrictions
    if "slot" in enchant and enchant["slot"] == "socket":
        return True

    # Default to False if no matching criteria
    return False


def get_base_name(enchant):
    # Remove rank indicators and quality indicators from the name
    name = enchant.get("baseDisplayName", enchant["displayName"])
    return re.sub(r"(\s+\d+|\s+[IVX]+)$", "", name)


def get_rank(enchant):
    # Extract the rank number from the name or use craftingQuality
    name = enchant["displayName"]
    rank_match = re.search(r"\s+(\d+)$", name)
    if rank_match:
        return int(rank_match.group(1))
    elif "craftingQuality" in enchant:
        return enchant["craftingQuality"]
    else:
        return 1  # Default rank if no rank information is found


def filter_enchants(enchants, current_expansion):
    filtered_enchants = []
    grouped_enchants = defaultdict(list)

    for enchant in enchants:
        if enchant.get(
            "expansion"
        ) == current_expansion and is_usable_by_demon_hunter_enchant(enchant):
            # Only consider enchants with craftingQuality 3 or those without craftingQuality
            if "craftingQuality" not in enchant or enchant["craftingQuality"] == 3:
                base_name = enchant.get("baseDisplayName", enchant["displayName"])
                grouped_enchants[base_name].append(enchant)

    for base_name, group in grouped_enchants.items():
        # If there's only one enchant in the group, add it
        if len(group) == 1:
            filtered_enchants.append(group[0])
        else:
            # If there are multiple enchants, prefer the one with craftingQuality 3
            crafted_enchants = [e for e in group if e.get("craftingQuality") == 3]
            if crafted_enchants:
                filtered_enchants.append(crafted_enchants[0])
            else:
                # If no craftingQuality 3, just take the first one (should not happen with our filtering)
                filtered_enchants.append(group[0])

    return filtered_enchants


def is_relevant_consumable(item, current_expansion):
    if item is None:
        return False

    # Check if it's a current expansion item
    if item.get("expansion") != current_expansion:
        return False

    # Include only rank 3 consumables
    if item.get("craftingQuality") != 3:
        return False

    return True


def filter_consumables(data, current_expansion, data_type):
    filtered_consumables = []
    if data_type == "crafting":
        items = data["reagents"]
    else:  # potions or flasks
        items = data

    for item in items:
        if is_relevant_consumable(item, current_expansion):
            filtered_consumables.append(item)
    return filtered_consumables


def is_embellishment(item, current_expansion):
    if item is None:
        return False

    # Check for crafting embellishments
    if (
        item.get("craftingQuality") == 3
        and item.get("expansion") == current_expansion
        and item.get("craftingBonusIds")
        and item.get("itemLimit", {}).get("quantity") == 2
    ):
        return True

    # Check for item embellishments
    if (
        item.get("expansion") == current_expansion
        and item.get("itemLimit", {}).get("quantity") == 2
        and item.get("bonusLists")
        and item.get("profession", {}).get("optionalCraftingSlots")
    ):
        return True

    return False


def filter_item_embellishments(items, current_expansion):
    return [item for item in items if is_embellishment(item, current_expansion)]


def filter_embellishments(crafting_data, current_expansion):
    filtered_embellishments = []
    reagents = crafting_data.get("reagents", [])
    for item in reagents:
        if item is not None and is_embellishment(item, current_expansion):
            filtered_embellishments.append(item)
    return filtered_embellishments


def main():
    items_url = "https://www.raidbots.com/static/data/live/equippable-items.json"
    enchants_url = "https://www.raidbots.com/static/data/live/enchantments.json"
    crafting_url = "https://www.raidbots.com/static/data/live/crafting.json"
    potions_url = "https://www.raidbots.com/static/data/live/potions.json"
    flasks_url = "https://www.raidbots.com/static/data/live/flasks.json"
    current_expansion = 10  # Dragonflight

    print("Fetching items data...")
    all_items = load_data_from_url(items_url)
    print("Fetching enchants data...")
    all_enchants = load_data_from_url(enchants_url)
    print("Fetching crafting data...")
    all_crafting = load_data_from_url(crafting_url)
    print("Fetching potions data...")
    all_potions = load_data_from_url(potions_url)
    print("Fetching flasks data...")
    all_flasks = load_data_from_url(flasks_url)

    print("Filtering items...")
    filtered_items = filter_items(all_items, current_expansion)

    print(f"Total items: {len(all_items)}")
    print(f"Filtered items for Demon Hunters: {len(filtered_items)}")

    # Save filtered items
    with open(get_data_file_path("filtered_items.json"), "w") as file:
        json.dump(filtered_items, file, indent=2)

    print("Filtering enchants...")
    filtered_enchants = filter_enchants(all_enchants, current_expansion)

    print(f"\nTotal enchants: {len(all_enchants)}")
    print(f"Filtered enchants for Demon Hunters: {len(filtered_enchants)}")

    # Save filtered enchants
    with open(get_data_file_path("filtered_enchants.json"), "w") as file:
        json.dump(filtered_enchants, file, indent=2)

    print("Filtering consumables...")
    filtered_potions = filter_consumables(all_potions, current_expansion, "potions")
    filtered_flasks = filter_consumables(all_flasks, current_expansion, "flasks")

    all_filtered_consumables = filtered_potions + filtered_flasks

    print("Filtering embellishments...")
    crafting_embellishments = filter_embellishments(all_crafting, current_expansion)
    item_embellishments = filter_item_embellishments(all_items, current_expansion)

    # Combine both lists of embellishments
    all_embellishments = crafting_embellishments + item_embellishments

    # Remove duplicates based on item ID
    unique_embellishments = {emb["id"]: emb for emb in all_embellishments}.values()
    filtered_embellishments = list(unique_embellishments)

    # Save filtered embellishments
    with open(get_data_file_path("filtered_embellishments.json"), "w") as file:
        json.dump(filtered_embellishments, file, indent=2)

    # Save filtered consumables
    with open(get_data_file_path("filtered_consumables.json"), "w") as file:
        json.dump(all_filtered_consumables, file, indent=2)

    print("Filtering complete. Results saved in the /data folder.")
    print(f"\nTotal crafting categories: {len(all_crafting)}")
    print(f"Filtered potions: {len(all_potions)}")
    print(f"Filtered flasks: {len(all_flasks)}")
    print(f"Filtered consumables: {len(all_filtered_consumables)}")
    print(f"Filtered embellishments: {len(filtered_embellishments)}")


if __name__ == "__main__":
    main()
