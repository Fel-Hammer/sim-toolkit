import json
import re
from collections import defaultdict
import requests
import os
import logging

logging.basicConfig(level=logging.DEBUG, format="%(message)s")


SLOT_MAP = {
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
    13: "weapon",
    14: "shield",
    15: "ranged",
    16: "back",
    17: "two_hand",
    18: "bag",
    19: "tabard",
    20: "robe",
    21: "main_hand",
    22: "off_hand",
    23: "holdable",
    24: "ammo",
    25: "thrown",
    26: "ranged_right",
    27: "quiver",
    28: "relic",
}

DH_USABLE_SLOTS = {
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "wrists",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger",
    "trinket",
    "main_hand",
    "off_hand",
}


def get_data_file_path(filename):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(os.path.dirname(script_dir), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, filename)


def load_data_from_url(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def is_embellishment(item):
    if item is None:
        return False
    item_limit = item.get("itemLimit", {})
    return item_limit.get("category") == 512 and item_limit.get("quantity") == 2


def is_usable_by_demon_hunter(item):
    DH_CLASS_ID = 12
    if "allowableClasses" in item and DH_CLASS_ID not in item["allowableClasses"]:
        return False

    item_class = item.get("itemClass")
    item_subclass = item.get("itemSubClass")
    inventory_type = item.get("inventoryType")

    if item_class == 4:  # Armor
        if item_subclass == 2:  # Leather
            return True
        if item_subclass == 0:  # Misc accessories
            if inventory_type in [2, 11]:  # Neck, Finger
                return True
            if inventory_type == 12:  # Trinket
                return is_valid_trinket_for_demon_hunter(item)
    elif item_class == 2:  # Weapon
        dh_weapon_types = [
            0,
            4,
            7,
            13,
        ]  # One-handed axes, Fist weapons, One-handed swords, Warglaives
        return item_subclass in dh_weapon_types and inventory_type in [
            13,
            21,
            22,
        ]  # One-Hand, Main Hand, Off Hand
    return False


def is_valid_trinket_for_demon_hunter(item):
    if "stats" not in item:
        return True

    agility_stat_ids = [3, 71, 72, 73]  # Agility or any combo including Agility
    primary_stat_ids = [3, 4, 5, 71, 72, 73, 74]  # All primary stats and combinations

    item_stats = [stat["id"] for stat in item["stats"]]

    has_agility = any(stat_id in agility_stat_ids for stat_id in item_stats)
    has_any_primary_stat = any(stat_id in primary_stat_ids for stat_id in item_stats)

    # Include if it has agility or if it has no primary stats
    return has_agility or not has_any_primary_stat


def is_pvp_item(item):
    pvp_prefixes = ["Gladiator", "Combatant", "Aspirant", "Veteran"]
    return (
        any(prefix in item["name"] for prefix in pvp_prefixes)
        or re.search(r"S\d+", item["name"])
        or item.get("pvp", False)
    )


def is_from_specific_dungeon(item):
    specific_dungeon_ids = {1271, 1274, 1269, 1270, 1184, 1182, 1023, 71}
    return any(
        source["instanceId"] in specific_dungeon_ids
        for source in item.get("sources", [])
    )


def filter_items(items, current_expansion):
    return [
        item
        for item in items
        if all(
            key in item
            for key in [
                "itemClass",
                "itemSubClass",
                "inventoryType",
                "quality",
                "expansion",
            ]
        )
        and is_usable_by_demon_hunter(item)
        and not is_pvp_item(item)
        and (
            (is_from_specific_dungeon(item) and item["quality"] >= 3)
            or (item["expansion"] == current_expansion and item["quality"] >= 2)
        )
    ]


def affects_damage(enchant):
    damage_stats = {
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
    }
    if any(stat["type"].lower() in damage_stats for stat in enchant.get("stats", [])):
        return True

    display_name = enchant["displayName"].lower()
    damage_keywords = {
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
    }
    if any(keyword in display_name for keyword in damage_keywords):
        return True

    special_damage_enchants = {
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
    }
    if any(keyword in enchant["displayName"] for keyword in special_damage_enchants):
        return True

    damage_categories = {
        "Chest Enchantments",
        "Weapon Enchantments",
        "Ring Enchantments",
    }
    return enchant.get("categoryName") in damage_categories


def is_usable_by_demon_hunter_enchant(enchant):
    if enchant.get("categoryName") == "Runes":
        return False

    if "stats" in enchant:
        stat_types = {stat["type"].lower() for stat in enchant["stats"]}
        if "int" in stat_types or "intellect" in stat_types:
            if not stat_types & {
                "agi",
                "agility",
                "str",
                "strength",
                "stragi",
                "stragiint",
            }:
                return False

    if not affects_damage(enchant):
        return False

    if "equipRequirements" in enchant:
        req = enchant["equipRequirements"]
        if req["itemClass"] == 2:
            dh_weapon_mask = 0b1000000000000011110001  # Warglaives, Swords, Axes, Fist Weapons, Daggers
            if req["itemSubClassMask"] & dh_weapon_mask:
                return True
        elif req["itemClass"] == 4:
            dh_armor_mask = 0b110  # Leather and Cloth
            if req["itemSubClassMask"] & dh_armor_mask:
                return True

    return enchant.get("slot") == "socket"


def get_rank(enchant):
    name = enchant["displayName"]
    rank_match = re.search(r"\s+(\d+)$", name)
    if rank_match:
        return int(rank_match.group(1))
    return enchant.get("craftingQuality", 1)


def filter_enchants(enchants, current_expansion):
    filtered_enchants = []
    grouped_enchants = defaultdict(list)

    for enchant in enchants:
        if (
            enchant.get("expansion") == current_expansion
            and is_usable_by_demon_hunter_enchant(enchant)
            and (
                enchant.get("craftingQuality", 1) == 3
                or "craftingQuality" not in enchant
            )
        ):
            base_name = enchant.get("baseDisplayName", enchant["displayName"])
            grouped_enchants[base_name].append(enchant)

    for group in grouped_enchants.values():
        if len(group) == 1:
            filtered_enchants.append(group[0])
        else:
            crafted_enchants = [e for e in group if e.get("craftingQuality") == 3]
            filtered_enchants.append(
                crafted_enchants[0] if crafted_enchants else group[0]
            )

    return filtered_enchants


def is_relevant_consumable(item, current_expansion):
    return (
        item is not None
        and item.get("expansion") == current_expansion
        and item.get("craftingQuality") == 3
    )


def filter_consumables(data, current_expansion, data_type):
    items = data["reagents"] if data_type == "crafting" else data
    return [item for item in items if is_relevant_consumable(item, current_expansion)]


def get_eligible_slots(embellishment_id, crafting_data, items_data):
    eligible_slots = set()
    reagent_slots = set()

    slots = crafting_data.get("slots", {})
    for slot_id, slot_data in slots.items():
        if embellishment_id in slot_data.get("itemIds", []):
            reagent_slots.add(int(slot_id))

    for item in items_data:
        if "profession" in item and "optionalCraftingSlots" in item["profession"]:
            optional_slots = {
                opt_slot["id"]
                for opt_slot in item["profession"]["optionalCraftingSlots"]
            }
            if reagent_slots & optional_slots:
                inv_type = item.get("inventoryType")
                if inv_type in SLOT_MAP and is_usable_by_demon_hunter(item):
                    eligible_slots.add(SLOT_MAP[inv_type])

    return list(eligible_slots)


def filter_embellishments(crafting_data, items_data, current_expansion):
    crafted_embellishments = []
    item_embellishments = []

    # Crafting category IDs for Darkmoon Sigils
    darkmoon_sigil_categories = {587, 588, 589, 590}

    # Process craftable embellishments from crafting_data
    for item in crafting_data.get("reagents", []):
        if (
            item is not None
            and is_embellishment(item)
            and item.get("expansion") == current_expansion
        ):

            category_id = item.get("craftingCategoryId")

            if category_id in darkmoon_sigil_categories:
                item["eligible_slots"] = ["weapon"]
                crafted_embellishments.append(item)
            else:
                eligible_slots = get_eligible_slots(
                    item["id"], crafting_data, items_data
                )
                if eligible_slots:
                    item["eligible_slots"] = eligible_slots
                    crafted_embellishments.append(item)

    # Process full item embellishments from items_data
    for item in items_data:
        if (
            item is not None
            and is_embellishment(item)
            and item.get("expansion") == current_expansion
            and is_usable_by_demon_hunter(item)
        ):
            inv_type = item.get("inventoryType")
            if inv_type in SLOT_MAP:
                item["eligible_slots"] = [SLOT_MAP[inv_type]]
                item_embellishments.append(item)

    all_embellishments = crafted_embellishments + item_embellishments
    filtered_embellishments = filter_highest_quality_embellishments(all_embellishments)

    return (
        filtered_embellishments,
        len(crafted_embellishments),
        len(item_embellishments),
    )


def filter_highest_quality_embellishments(embellishments):
    highest_quality = {}
    for emb in embellishments:
        if "Darkmoon Sigil" in emb["name"]:
            # Use the full name for Darkmoon Sigils
            key = emb["name"]
        else:
            # For other embellishments, use the base name
            key = emb["name"].split(":")[0] if ":" in emb["name"] else emb["name"]

        quality = emb.get("craftingQuality", 1)

        if (
            key not in highest_quality
            or quality > highest_quality[key]["craftingQuality"]
        ):
            highest_quality[key] = emb

    return list(highest_quality.values())


def main():
    urls = {
        "items": "https://www.raidbots.com/static/data/live/equippable-items.json?cb=123456789",
        "enchants": "https://www.raidbots.com/static/data/live/enchantments.json?cb=123456789",
        "crafting": "https://www.raidbots.com/static/data/live/crafting.json?cb=123456789",
        "potions": "https://www.raidbots.com/static/data/live/potions.json?cb=123456789",
        "flasks": "https://www.raidbots.com/static/data/live/flasks.json?cb=123456789",
    }
    current_expansion = 10  # The War Within

    print("Fetching data...")
    data = {key: load_data_from_url(url) for key, url in urls.items()}

    print("Filtering items...")
    filtered_items = filter_items(data["items"], current_expansion)
    print(f"Total items: {len(data['items'])}")
    print(f"Filtered items for Demon Hunters: {len(filtered_items)}")

    print("Filtering enchants...")
    filtered_enchants = filter_enchants(data["enchants"], current_expansion)
    print(f"Total enchants: {len(data['enchants'])}")
    print(f"Filtered enchants for Demon Hunters: {len(filtered_enchants)}")

    print("Filtering consumables...")
    filtered_potions = filter_consumables(data["potions"], current_expansion, "potions")
    filtered_flasks = filter_consumables(data["flasks"], current_expansion, "flasks")
    all_filtered_consumables = filtered_potions + filtered_flasks

    print("Filtering embellishments...")
    filtered_embellishments, crafted_count, item_count = filter_embellishments(
        data["crafting"], data["items"], current_expansion
    )

    # Separate Darkmoon Sigils and other embellishments
    darkmoon_sigils = [
        emb for emb in filtered_embellishments if "Darkmoon Sigil" in emb["name"]
    ]
    other_embellishments = [
        emb for emb in filtered_embellishments if "Darkmoon Sigil" not in emb["name"]
    ]

    # Log concise summary of embellishments
    print(f"Embellishment Summary:")
    print(f"  Total Unique Embellishments: {len(filtered_embellishments)}")
    print(f"    - Darkmoon Sigils: {len(darkmoon_sigils)}")
    print(f"    - Other Embellishments: {len(other_embellishments)}")
    print(f"  Breakdown by Source:")
    print(f"    - Crafted Embellishments: {crafted_count}")
    print(f"    - Item Embellishments: {item_count}")

    # Save filtered data
    for name, filtered_data in [
        ("items", filtered_items),
        ("enchants", filtered_enchants),
        ("embellishments", filtered_embellishments),
        ("consumables", all_filtered_consumables),
    ]:
        with open(get_data_file_path(f"filtered_{name}.json"), "w") as file:
            json.dump(filtered_data, file, indent=2)

    print("Filtering complete. Results saved in the /data folder.")
    print(f"Total crafting categories: {len(data['crafting'].get('reagents', []))}")
    print(f"Filtered potions: {len(filtered_potions)}")
    print(f"Filtered flasks: {len(filtered_flasks)}")
    print(f"Filtered consumables: {len(all_filtered_consumables)}")


if __name__ == "__main__":
    main()
