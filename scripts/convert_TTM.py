import re
from collections import defaultdict
import json

# Load the talent dictionary
with open('/Users/tom/Documents/GitHub/APL/talent_dictionary.json', 'r') as f:
    TALENT_DICT = json.load(f)

VENGEANCE_OFFENSIVE = {talent['simc_name']: talent['abbreviation'] for talent in TALENT_DICT['DEMON_HUNTER']['VENGEANCE_TALENTS'].values() if talent['talent_type'] == 'offensive'}
VENGEANCE_DEFENSIVE = {talent['simc_name']: talent['abbreviation'] for talent in TALENT_DICT['DEMON_HUNTER']['VENGEANCE_TALENTS'].values() if talent['talent_type'] == 'defensive'}
HAVOC_OFFENSIVE = {talent['simc_name']: talent['abbreviation'] for talent in TALENT_DICT['DEMON_HUNTER']['HAVOC_TALENTS'].values() if talent['talent_type'] == 'offensive'}
HAVOC_DEFENSIVE = {talent['simc_name']: talent['abbreviation'] for talent in TALENT_DICT['DEMON_HUNTER']['HAVOC_TALENTS'].values() if talent['talent_type'] == 'defensive'}

VENGEANCE_ABSENCE_INDICATORS = {
    "spirit_bomb": "NoSpB",
}

def create_unique_id(talents):
    offensive_parts = []
    defensive_parts = []

    is_vengeance = any("fel_devastation" in talent for talent in talents.split('/'))
    is_havoc = any("eye_beam" in talent for talent in talents.split('/'))

    if is_vengeance:
        offensive_talents = VENGEANCE_OFFENSIVE
        defensive_talents = VENGEANCE_DEFENSIVE
        absence_indicators = VENGEANCE_ABSENCE_INDICATORS
    elif is_havoc:
        offensive_talents = HAVOC_OFFENSIVE
        defensive_talents = HAVOC_DEFENSIVE
        absence_indicators = {}
    else:
        return "Unknown"

    talent_list = talents.split('/')

    for talent, abbrev in offensive_talents.items():
        if any(talent in t for t in talent_list):
            offensive_parts.append(abbrev)
        elif is_vengeance and talent in absence_indicators and not any(talent in t for t in talent_list):
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
    profile_name_dict = {}

    with open(input_file, 'r') as infile:
        for line in infile:
            match = re.match(r'profileset\."([^"]+)"\+="spec_talents=(.+)"', line.strip())
            if match:
                profile_name = match.group(1)
                talents = match.group(2)
                unique_id = create_unique_id(talents)
                talent_dict[talents].append(profile_name)
                unique_id_dict[talents] = unique_id
                profile_name_dict[profile_name] = talents

    with open(output_file, 'w') as outfile:
        for talents, profiles in talent_dict.items():
            if len(profiles) == 1:  # Only write non-duplicates
                unique_id = unique_id_dict[talents]
                template_string = f'$({unique_id})="{talents}"\n'
                outfile.write(template_string)

    return talent_dict, profile_name_dict

def check_duplicate_profile_names(profile_name_dict):
    profile_name_duplicates = defaultdict(list)
    for profile_name, talents in profile_name_dict.items():
        profile_name_duplicates[profile_name].append(talents)

    return {name: talents for name, talents in profile_name_duplicates.items() if len(talents) > 1}

# Usage
input_file = '/Users/tom/Documents/GitHub/APL/havoc/new-profileset.simc'
output_file = '/Users/tom/Documents/GitHub/APL/havoc/converted_profile_templates.simc'
talent_dict, profile_name_dict = convert_profilesets(input_file, output_file)

duplicate_templates = {talents: profiles for talents, profiles in talent_dict.items() if len(profiles) > 1}
duplicate_profile_names = check_duplicate_profile_names(profile_name_dict)

print(f"Number of duplicate talent combinations found: {len(duplicate_templates)}")
print(f"Number of duplicate profile names found: {len(duplicate_profile_names)}")