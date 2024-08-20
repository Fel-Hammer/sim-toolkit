import os
import json
import sys
import configparser
from typing import Dict, List, Union, Any


def read_config(config_path: str) -> Dict[str, str]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path)

    if "General" not in config:
        raise ValueError(f"Config file is missing the [General] section: {config_path}")

    required_keys = ["spec_name", "report_folder"]
    missing_keys = [key for key in required_keys if key not in config["General"]]
    if missing_keys:
        raise ValueError(
            f"Config file is missing required keys in [General] section: {', '.join(missing_keys)}"
        )

    return dict(config["General"])


def load_json_file(file_path: str) -> List[Dict]:
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_talent_info(talent_dict: Dict, talent_type: str, talent: str) -> str:
    talent_info = talent_dict.get(talent_type, {}).get(talent, talent)
    if isinstance(talent_info, list):
        return talent_info[1] if len(talent_info) > 1 else talent_info[0]
    return talent_info


def parse_build_name(
    build_name: str, talent_dict: Dict[str, Dict[str, Union[str, List[str]]]], spec: str
) -> Dict[str, Union[str, List[str]]]:
    parts = build_name.split()
    result = {"hero": "", "class": [], "offensive": [], "defensive": []}

    for part in parts:
        if part.startswith("[") and part.endswith("]"):
            talent = part.strip("[]").lower()
            # Find the matching hero talent in the talent dictionary
            for key, value in talent_dict["hero"].items():
                if talent in key.lower() or talent in value.lower():
                    result["hero"] = key
                    break
            else:
                raise ValueError(
                    f"Hero talent '{part.strip('[]')}' not found in talent dictionary"
                )
        elif part.startswith("(") and part.endswith(")"):
            talents = part.strip("()").split("_")
            result["class"] = [talent_dict["class"].get(t, [t, t])[1] for t in talents]
        elif "_" in part:
            talents = part.split("_")
            for t in talents:
                if t == "NoSpB":  # Special case for "No Spirit Bomb"
                    continue
                for talent_name, talent_info in talent_dict["spec"].items():
                    if talent_info[1] == t:
                        if talent_info[2] == "o" and talent_info[3] == spec[0].lower():
                            result["offensive"].append(t)
                        elif (
                            talent_info[2] == "d" and talent_info[3] == spec[0].lower()
                        ):
                            result["defensive"].append(t)
                        break
    return result


def process_data(
    data: Dict[str, Dict[str, Dict[str, Union[float, str]]]],
    talent_dict: Dict[str, Dict[str, Union[str, List[str]]]],
    spec: str,
) -> Dict[str, Dict[str, Dict[str, Union[float, str, List[str]]]]]:
    processed_data = {}

    for sim_type, sim_data in data.items():
        if sim_type == "DSlice" or (
            "_" in sim_type and sim_type.split("_")[0][-1] == "T"
        ):
            processed_data[sim_type] = {}

            # Sort builds by DPS for this sim_type
            sorted_builds = sorted(
                sim_data.items(), key=lambda x: x[1]["dps"], reverse=True
            )

            for rank, (build_name, build_data) in enumerate(sorted_builds, 1):
                if build_name.startswith("["):
                    build_info = parse_build_name(build_name, talent_dict, spec)
                    processed_data[sim_type][build_name] = {
                        **build_info,
                        "dps": build_data["dps"],
                        "talent_hash": build_data.get("talent_hash", ""),
                        "rank": rank,  # Add rank for this sim_type
                    }

    overall_ranks = calculate_overall_rank(processed_data)

    # Add overall rank to each build in each sim type
    for sim_type in processed_data:
        for build_name in processed_data[sim_type]:
            processed_data[sim_type][build_name]["overall_rank"] = overall_ranks[
                build_name
            ]

    total_builds = sum(len(sim_data) for sim_data in processed_data.values())
    print(f"Total processed builds: {total_builds}")

    return processed_data


def calculate_average_dps(build_data: Dict[str, Union[float, str, List[str]]]) -> float:
    dps_values = [value for key, value in build_data.items() if key.startswith("dps_")]
    return sum(dps_values) / len(dps_values) if dps_values else 0


def calculate_overall_rank(
    data: Dict[str, Dict[str, Dict[str, Union[float, str, List[str]]]]]
) -> Dict[str, int]:
    builds = list(next(iter(data.values())).keys())
    sim_types = list(data.keys())

    # Calculate rank for each build within each simulation type
    ranks = {sim_type: {} for sim_type in sim_types}
    for sim_type in sim_types:
        sorted_builds = sorted(
            builds, key=lambda x: data[sim_type][x]["dps"], reverse=True
        )
        for rank, build in enumerate(sorted_builds, 1):
            ranks[sim_type][build] = rank

    # Calculate average rank across all simulation types
    average_ranks = {}
    for build in builds:
        avg_rank = sum(ranks[sim_type][build] for sim_type in sim_types) / len(
            sim_types
        )
        average_ranks[build] = avg_rank

    # Sort builds based on average rank and assign overall rank
    sorted_builds = sorted(average_ranks.items(), key=lambda x: x[1])
    overall_ranks = {build: rank for rank, (build, _) in enumerate(sorted_builds, 1)}

    return overall_ranks


def generate_html(
    data: Dict[str, Dict[str, Dict[str, Union[float, str, List[str]]]]],
    raw_data: Dict[str, Any],
    spec_name: str,
    talent_dict: Dict[str, Dict[str, Union[str, List[str]]]],
) -> str:
    sim_types = list(data.keys())
    builds = []

    for sim_type, sim_data in data.items():
        for build_name, build_data in sim_data.items():
            existing_build = next(
                (b for b in builds if b["talent_hash"] == build_data["talent_hash"]),
                None,
            )
            if existing_build is None:
                new_build = {
                    "hero": build_data["hero"],
                    "class": build_data["class"],
                    "offensive": build_data["offensive"],
                    "defensive": build_data["defensive"],
                    "talent_hash": build_data["talent_hash"],
                    "dps": {},
                    "rank": {},
                    "overall_rank": build_data["overall_rank"],
                }
                builds.append(new_build)
                existing_build = new_build

            existing_build["dps"][sim_type] = round(build_data["dps"], 2)
            existing_build["rank"][sim_type] = build_data["rank"]

    builds.sort(key=lambda x: x["overall_rank"])
    for index, build in enumerate(builds, 1):
        build["overall_rank"] = index

    json_data = {"builds": builds, "sim_types": sim_types}

    # Create additionalData dictionary
    additional_data = {
        key: value for key, value in raw_data.items() if key not in sim_types
    }

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    try:
        with open(os.path.join(root_dir, "template.html"), "r", encoding="utf-8") as f:
            html_template = f.read()
        with open(os.path.join(root_dir, "styles.css"), "r", encoding="utf-8") as f:
            css_content = f.read()
        with open(os.path.join(root_dir, "script.js"), "r", encoding="utf-8") as f:
            js_content = f.read()
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Required file not found: {e.filename}")

    js_with_data = f"""
    const rawData = {json.dumps(json_data)};
    const additionalData = {json.dumps(additional_data)};
    const talentDictionary = {json.dumps(talent_dict)};
    const specName = "{spec_name}";
    {js_content}
    """

    return (
        html_template.replace("$TITLE", f"{spec_name} Demon Hunter Simulations")
        .replace("$STYLES", css_content)
        .replace("$SCRIPT", js_with_data)
        .replace("$TABLE_HEADERS", "<th>Build</th><th>DPS</th><th>Rank</th>")
    )


def process_additional_data(additional_data: Dict[str, Any]) -> Dict[str, Any]:
    processed_data = {}
    for section, items in additional_data.items():
        if isinstance(items, dict) and all(
            isinstance(sub_items, dict) for sub_items in items.values()
        ):
            processed_data[section] = {}
            for variant, sub_items in items.items():
                if all(
                    isinstance(item, dict) and "dps" in item
                    for item in sub_items.values()
                ):
                    best_dps = max(item["dps"] for item in sub_items.values())
                    processed_items = {}
                    for name, item in sub_items.items():
                        dps_diff = item["dps"] - best_dps
                        processed_items[name] = {
                            **item,
                            "dps_diff": round(dps_diff, 2),
                            "percent_diff": round((dps_diff / best_dps) * 100, 2),
                        }
                    processed_data[section][variant] = processed_items
                else:
                    processed_data[section][variant] = sub_items
        else:
            processed_data[section] = items
    return processed_data


def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_reports.py <config_file>")
        sys.exit(1)

    try:
        config = read_config(sys.argv[1])
        spec_name = config["spec_name"]
        report_folder = config["report_folder"]

        print(f"Generating report for {spec_name} spec")

        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        simulation_file = os.path.join(
            root_dir, report_folder, "simulation_results.json"
        )
        talent_dict_file = os.path.join(root_dir, "talent_dictionary.json")

        for file_path in [simulation_file, talent_dict_file]:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Required file not found: {file_path}")

        raw_data = load_json_file(simulation_file)
        talent_dict = load_json_file(talent_dict_file)
        processed_data = process_data(raw_data, talent_dict, spec_name)

        print("\nProcessed simulation types:")
        print(", ".join(processed_data.keys()))

        print("\nAdditional data sections:")
        additional_sections = set(raw_data.keys()) - set(processed_data.keys())
        print(", ".join(additional_sections))

        # Process additional data
        additional_data = {key: raw_data[key] for key in additional_sections}
        processed_additional_data = process_additional_data(additional_data)

        html = generate_html(
            processed_data, processed_additional_data, spec_name, talent_dict
        )

        output_folder = os.path.join(root_dir, f"website_{spec_name.lower()}")
        os.makedirs(output_folder, exist_ok=True)
        output_path = os.path.join(output_folder, f"{spec_name.lower()}.html")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"\nReport generated for {spec_name} spec at {output_path}")

    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
