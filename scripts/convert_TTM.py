import re
from collections import defaultdict
import json

# Load the talent dictionary
with open("/Users/tom/Documents/GitHub/sim-toolkit/talent_dictionary.json", "r") as f:
    TALENT_DICT = json.load(f)


def create_talent_dict(spec, talent_type):
    return {
        talent: info[1] if isinstance(info, list) and len(info) > 1 else info
        for talent, info in TALENT_DICT["spec"].items()
        if isinstance(info, list)
        and len(info) > 2
        and info[2] == talent_type[0]
        and info[3] == spec[0]
    }


VENGEANCE_OFFENSIVE = create_talent_dict("vengeance", "offensive")
VENGEANCE_DEFENSIVE = create_talent_dict("vengeance", "defensive")
HAVOC_OFFENSIVE = create_talent_dict("havoc", "offensive")
HAVOC_DEFENSIVE = create_talent_dict("havoc", "defensive")

VENGEANCE_ABSENCE_INDICATORS = {"spirit_bomb": "NoSpB"}

ALL_TALENTS = (
    set(VENGEANCE_OFFENSIVE)
    | set(VENGEANCE_DEFENSIVE)
    | set(HAVOC_OFFENSIVE)
    | set(HAVOC_DEFENSIVE)
)

# Manual filter for talents to exclude
MANUAL_FILTER = {"momentum"}


def create_unique_id(talents):
    offensive_parts, defensive_parts = [], []
    is_vengeance = "fel_devastation" in talents
    offensive_talents = VENGEANCE_OFFENSIVE if is_vengeance else HAVOC_OFFENSIVE
    defensive_talents = VENGEANCE_DEFENSIVE if is_vengeance else HAVOC_DEFENSIVE
    absence_indicators = VENGEANCE_ABSENCE_INDICATORS if is_vengeance else {}

    talent_list = talents.split("/")

    for talent, abbrev in offensive_talents.items():
        if any(talent in t for t in talent_list):
            offensive_parts.append(abbrev)
        elif (
            is_vengeance
            and talent in absence_indicators
            and not any(talent in t for t in talent_list)
        ):
            offensive_parts.append(absence_indicators[talent])

    for talent, abbrev in defensive_talents.items():
        if any(talent in t for t in talent_list):
            defensive_parts.append(abbrev)

    offensive_id = "_".join(offensive_parts) or "Base"
    defensive_id = "_".join(defensive_parts) or "NoDefensive"

    return f"{offensive_id}__{defensive_id}"


def convert_profilesets(input_file, output_file):
    talent_dict = defaultdict(list)
    unique_id_dict = {}
    unknown_talents = set()
    filtered_profiles = []

    with open(input_file, "r") as infile:
        for line in infile:
            if match := re.match(
                r'profileset\."([^"]+)"\+="spec_talents=(.+)"', line.strip()
            ):
                profile_name, talents = match.groups()

                # Skip profiles containing filtered talents
                if any(filtered_talent in talents for filtered_talent in MANUAL_FILTER):
                    filtered_profiles.append(profile_name)
                    continue

                unique_id = create_unique_id(talents)
                talent_dict[talents].append(profile_name)
                unique_id_dict[talents] = unique_id

                # Check for unknown talents
                for talent in talents.split("/"):
                    talent_name = talent.split(":")[0]
                    if (
                        talent_name not in ALL_TALENTS
                        and talent_name not in MANUAL_FILTER
                    ):
                        unknown_talents.add(talent_name)

    with open(output_file, "w") as outfile:
        for talents, unique_id in unique_id_dict.items():
            outfile.write(f'$({unique_id})="{talents}"\n')

    return talent_dict, unknown_talents, filtered_profiles


def check_duplicate_talents(talent_dict):
    return {
        talents: profiles
        for talents, profiles in talent_dict.items()
        if len(profiles) > 1
    }


if __name__ == "__main__":
    input_file = "/Users/tom/Documents/GitHub/sim-toolkit/havoc/new-profileset.simc"
    output_file = "/Users/tom/Documents/GitHub/sim-toolkit/havoc/converted_profile_templates_two.simc"

    talent_dict, unknown_talents, filtered_profiles = convert_profilesets(
        input_file, output_file
    )
    duplicate_talents = check_duplicate_talents(talent_dict)

    print(f"Number of unique talent combinations: {len(talent_dict)}")
    print(
        f"Number of talent combinations with multiple profiles: {len(duplicate_talents)}"
    )

    if unknown_talents:
        print("\nUnknown talents (not in talent dictionary and not manually filtered):")
        for talent in sorted(unknown_talents):
            print(talent)

    print("\nManually filtered talents:")
    for talent in sorted(MANUAL_FILTER):
        print(talent)
