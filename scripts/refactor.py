import argparse
import configparser
import os
import json
import re
import subprocess
import sys
import time
import itertools
import tempfile
import logging
import pickle
import shutil
import glob
from downloadsimc import download_and_extract_simc
from abc import ABC, abstractmethod
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Union, Any
from talenthasher import generate_talent_hash, initialize_talent_data

# Set up logging
logging.basicConfig(level=logging.INFO, format=" %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


def file_operation_handler(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IOError as e:
            operation = func.__name__.replace("_", " ").capitalize()
            file_path = args[1] if len(args) > 1 else kwargs.get("file_path", "unknown")
            logger.error(f"Error during {operation} for file {file_path}: {e}")
            return None if "read" in func.__name__ else False

    return wrapper


class FileHandler:
    @staticmethod
    @file_operation_handler
    def ensure_directory(directory: str) -> bool:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")
        return True

    @staticmethod
    @file_operation_handler
    def read_file(file_path: str, mode="r") -> Optional[Union[str, bytes]]:
        with open(file_path, mode) as f:
            return f.read()

    @staticmethod
    @file_operation_handler
    def write_file(file_path: str, content: Union[str, bytes], mode="w") -> bool:
        with open(file_path, mode) as f:
            f.write(content)
        logger.debug(f"Successfully wrote to file: {file_path}")
        return True

    @staticmethod
    @file_operation_handler
    def create_temp_file(
        content: str,
        prefix: str = "temp_",
        suffix: str = ".simc",
        dir: Optional[str] = None,
    ) -> Optional[str]:
        with tempfile.NamedTemporaryFile(
            mode="w", prefix=prefix, suffix=suffix, dir=dir, delete=False
        ) as temp_file:
            temp_file.write(content)
            return temp_file.name

    @staticmethod
    @file_operation_handler
    def safe_delete(file_path: str) -> bool:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"File {file_path} deleted successfully.")
            return True
        logger.debug(f"File not found for deletion: {file_path}")
        return False

    @staticmethod
    def file_exists(file_path: str) -> bool:
        return os.path.exists(file_path)

    @staticmethod
    def join_path(*args: str) -> str:
        return os.path.join(*args)

    @staticmethod
    @file_operation_handler
    def copy_file(src: str, dst: str) -> bool:
        shutil.copy2(src, dst)
        logger.debug(f"Successfully copied file from {src} to {dst}")
        return True

    @staticmethod
    @file_operation_handler
    def create_file_if_not_exists(file_path: str, default_content: str = "") -> bool:
        if not FileHandler.file_exists(file_path):
            return FileHandler.write_file(file_path, default_content)
        return True

    @staticmethod
    def check_output_file(output_path: str) -> bool:
        if not FileHandler.file_exists(output_path):
            logger.error(f"Expected output file not found: {output_path}")
            return False
        return True

    @staticmethod
    def get_supplemental_file_path(folder: str, filename: str) -> Optional[str]:
        file_path = FileHandler.join_path(folder, filename)
        if not FileHandler.file_exists(file_path):
            logger.warning(f"Supplemental file not found: {filename}")
            return None
        return file_path


class ProgressTracker:
    def __init__(self, total_simulations: int):
        self.total_simulations = total_simulations
        self.current_simulation = 1
        self.update_interval = 0.5  # Update every 0.5 seconds
        self.last_update_time = 0
        self.progress_type = None
        self.total_profiles = 0
        self.current_profile = 0
        self.last_line = ""
        self.terminal_width = shutil.get_terminal_size().columns

    def update(self, line: str):
        current_time = time.time()
        self.terminal_width = shutil.get_terminal_size().columns
        if current_time - self.last_update_time < self.update_interval:
            return

        new_progress_type = self._detect_progress_type(line)

        if new_progress_type:
            if new_progress_type != self.progress_type:
                logger.debug(
                    f"Progress type changed from {self.progress_type} to {new_progress_type}"
                )
                self.progress_type = new_progress_type
                # Reset progress counters when switching types
                self.current_profile = 0
                self.total_profiles = 0

        if self.progress_type:
            getattr(self, f"_update_{self.progress_type}")(line)

        self.last_update_time = current_time
        self.last_line = line

    def set_progress_type(self, progress_type: str):
        if progress_type != self.progress_type:
            logger.debug(
                f"Progress type manually set from {self.progress_type} to {progress_type}"
            )
            self.progress_type = progress_type
            # Reset progress counters when switching types
            self.current_profile = 0
            self.total_profiles = 0

    def _detect_progress_type(self, line: str) -> Optional[str]:
        if "Generating Baseline:" in line:
            return "single_sim"
        elif "Profilesets" in line:
            return "multi_sim"
        elif "Generating Profileset:" in line:
            return "supplemental"
        elif "/" in line and not any(
            keyword in line for keyword in ["Generating", "Profilesets"]
        ):
            return "talent_hashing"
        return None

    def _update_talent_hashing(self, line: str):
        match = re.search(r"(\d+)/(\d+)", line)
        if match:
            current, total = map(int, match.groups())
            self._print_progress(
                f"[Talent Hashing] [Progress: {current}/{total}]", current / total
            )

    def _update_single_sim(self, line: str):
        match = re.search(r"Generating Baseline: (\d+)/(\d+) \[([=>.\s]+)\](.*)", line)
        if match:
            current, total, progress_bar, extra_info = match.groups()
            self.total_profiles = int(total)
            self.current_profile = int(current)
            self._print_progress(
                f"[Sim: {self.current_simulation}/{self.total_simulations}] [Profile: {current}/{total}]",
                self.current_profile / self.total_profiles,
                progress_bar,
                extra_info,
            )

    def _update_multi_sim(self, line: str):
        match = re.search(r"Profilesets.*?(\d+)/(\d+)\s+\[([=>.\s]+)\](.*)", line)
        if match:
            current, total, progress_bar, extra_info = match.groups()
            self.total_profiles = int(total)
            self.current_profile = int(current)
            self._print_progress(
                f"[Sim: {self.current_simulation}/{self.total_simulations}] [Profile: {current}/{total}]",
                self.current_profile / self.total_profiles,
                progress_bar,
                extra_info,
            )

    def _update_supplemental(self, line: str):
        match = re.search(
            r"Generating Profileset: (.*?) (\d+)/(\d+)\s+\[([=>.\s]+)\](.*)", line
        )
        if match:
            profileset_name, current, total, progress_bar, extra_info = match.groups()
            self.total_profiles = int(total)
            self.current_profile = int(current)
            self._print_progress(
                f"[Sim: {self.current_simulation}/{self.total_simulations}] [Profile: {current}/{total}] [{profileset_name}]",
                self.current_profile / self.total_profiles,
                progress_bar,
                extra_info,
            )

    def _print_progress(
        self,
        prefix: str,
        progress: float,
        progress_bar: str = None,
        extra_info: str = "",
    ):
        if progress_bar is None:
            progress_bar = self._generate_progress_bar(progress)

        extra_info = re.sub(
            r"Mean=\d+", "", extra_info
        )  # Remove Mean=xxx from extra_info

        # Truncate the profile name in the prefix
        prefix_parts = prefix.split("]")
        if len(prefix_parts) > 2:
            profile_name = prefix_parts[1].strip()[1:]  # Remove leading '['
            truncated_name = profile_name[:20] + (
                "..." if len(profile_name) > 20 else ""
            )
            prefix = f"{prefix_parts[0]}] [{truncated_name}]"

        output = f"\r{prefix} [{progress_bar}] {extra_info.strip()}"

        # Pad the output to fill the entire line and add a carriage return
        padding = max(self.terminal_width - len(output), 0) * " "
        padded_output = output + padding + "\r"

        print(padded_output, end="", flush=True)

    def _generate_progress_bar(self, progress: float, length: int = 20) -> str:
        filled_length = int(length * progress)
        return "=" * filled_length + ">" + "." * (length - filled_length - 1)

    def start_new_simulation(self):
        self.current_simulation += 1
        self.current_profile = 0
        self.total_profiles = 0
        print()  # Move to a new line for the next simulation

    def set_total_simulations(self, total: int):
        self.total_simulations = total


@dataclass
class SimulationParameters:
    iterations: int
    target_error: float
    targets: Optional[int] = None
    time: Optional[int] = None
    fight_style: Optional[str] = None
    sim_id: str = field(
        default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    )


@dataclass
class SimConfig:
    config_path: str
    script_dir: str
    spec_name: str
    simc_path: str
    apl_folder: str
    report_folder: str
    single_sim: bool
    talents: str
    iterations: int
    target_error: float
    multi_sim: str
    targets: int
    time: int
    clear_cache: bool = False
    json_output: bool = True
    html_output: bool = False
    supplemental_profilesets: bool = False
    generate_combined_apl: bool = False
    generate_website: bool = False
    debug: bool = False
    threads: int = 1
    profileset_work_threads: int = 1
    talent_strings: Dict[str, Dict[str, str]] = None
    timestamp: bool = False

    @classmethod
    def from_file(cls, config_path: str):
        config = configparser.ConfigParser()
        config.read(config_path)

        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)

        def get_path(section: str, option: str) -> str:
            return FileHandler.join_path(project_root, config.get(section, option))

        instance = cls(
            config_path=config_path,
            script_dir=script_dir,
            spec_name=config.get("General", "spec_name", fallback="Vengeance"),
            simc_path=config.get("General", "simc", fallback=""),
            apl_folder=get_path("General", "apl_folder"),
            report_folder=get_path("General", "report_folder"),
            single_sim=config.getboolean("Simulations", "single_sim", fallback=False),
            talents=config.get("Simulations", "talents", fallback=""),
            iterations=config.getint("Simulations", "iterations", fallback=10000),
            target_error=config.getfloat("Simulations", "target_error", fallback=0.2),
            multi_sim=config.get("Simulations", "multi_sim", fallback="").strip(),
            targets=config.getint("Simulations", "targets", fallback=1),
            time=config.getint("Simulations", "time", fallback=300),
            timestamp=config.getboolean("General", "timestamp", fallback=False),
            clear_cache=config.getboolean("General", "clear_cache", fallback=False),
            json_output=config.getboolean("General", "json_output", fallback=True),
            html_output=config.getboolean("General", "html_output", fallback=False),
            supplemental_profilesets=config.getboolean(
                "PostProcessing", "supplemental_profilesets", fallback=False
            ),
            generate_combined_apl=config.getboolean(
                "PostProcessing", "generate_combined_apl", fallback=False
            ),
            generate_website=config.getboolean(
                "PostProcessing", "generate_website", fallback=False
            ),
            debug=config.getboolean("General", "debug", fallback=False),
            threads=config.getint("Simulations", "threads", fallback=1),
            profileset_work_threads=config.getint(
                "Simulations", "profileset_work_threads", fallback=1
            ),
        )

        instance.check_and_set_simc_path()
        return instance

    def check_and_set_simc_path(self):
        if not self.simc_path:
            # Check if simc exists in the project
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            possible_paths = [
                os.path.join(project_root, "simc"),
                os.path.join(script_dir, "simc"),
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    self.simc_path = path
                    logger.info(f"Found SimC executable at: {self.simc_path}")
                    return

            # If not found, download it to the scripts folder
            try:
                self.simc_path = download_and_extract_simc()
                logger.info(f"Downloaded SimC executable to: {self.simc_path}")
            except Exception as e:
                logger.error(f"Error downloading SimulationCraft: {str(e)}")
                raise RuntimeError(
                    "Failed to locate or download SimulationCraft executable"
                )
        else:
            if not os.path.exists(self.simc_path):
                raise FileNotFoundError(
                    f"SimC executable not found at specified path: {self.simc_path}"
                )

    def parse_sim_parameters(self) -> List[SimulationParameters]:
        if self.single_sim or not self.multi_sim:
            fight_style = (
                "DungeonSlice"
                if str(self.targets).lower() == "dungeonslice"
                else "Patchwerk"
            )
            return [
                SimulationParameters(
                    iterations=self.iterations,
                    target_error=self.target_error,
                    targets=None if fight_style == "DungeonSlice" else self.targets,
                    time=self.time,
                    fight_style=fight_style,
                )
            ]

        sim_params = []
        for combo in self.multi_sim.split():
            if combo.lower() == "dungeonslice":
                sim_params.append(
                    SimulationParameters(
                        iterations=self.iterations,
                        target_error=self.target_error,
                        targets=None,
                        time=self.time,
                        fight_style="DungeonSlice",
                    )
                )
            else:
                targets, time = map(int, combo.split(","))
                sim_params.append(
                    SimulationParameters(
                        iterations=self.iterations,
                        target_error=self.target_error,
                        targets=targets,
                        time=time,
                        fight_style="Patchwerk",
                    )
                )

        return sim_params


class CacheManager:
    def __init__(self, config: SimConfig):
        self.config = config
        self.cache_file = FileHandler.join_path(
            config.script_dir, "simulation_cache.pkl"
        )
        self.cache = self.load_cache()
        self.modified = False

    def load_cache(self) -> Dict[str, Any]:
        if not FileHandler.file_exists(self.cache_file):
            logger.info(
                f"Cache file {self.cache_file} does not exist. Creating a new cache."
            )
            return {}

        try:
            content = FileHandler.read_file(self.cache_file, mode="rb")
            if content is None:
                return {}
            return pickle.loads(content)
        except Exception as e:
            logger.warning(f"Error loading cache: {e}. Starting with a new cache.")
            self._remove_corrupted_cache()
            return {}

    def _remove_corrupted_cache(self):
        if FileHandler.safe_delete(self.cache_file):
            logger.info(f"Removed corrupted cache file: {self.cache_file}")
        else:
            logger.error(f"Failed to remove corrupted cache file: {self.cache_file}")

    def save_cache(self):
        if not self.modified:
            return

        try:
            cache_content = pickle.dumps(self.cache)
            if FileHandler.write_file(self.cache_file, cache_content, mode="wb"):
                self.modified = False
                logger.info("Cache saved successfully")
            else:
                logger.error("Failed to save cache")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.cache.get(key, default)

    def set(self, key: str, value: Any):
        self.cache[key] = value
        self.modified = True

    def clear(self):
        self.cache.clear()
        self.modified = True

    def force_save(self):
        self.save_cache()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save_cache()


class TalentManager:
    def __init__(
        self,
        config: SimConfig,
        cache_manager: CacheManager,
        progress_tracker: ProgressTracker,
    ):
        self.config = config
        self.cache_manager = cache_manager
        self.progress_tracker = progress_tracker
        self.clear_cache_if_needed()

    def clear_cache_if_needed(self):
        if self.config.clear_cache:
            logger.info("Clearing talent cache...")
            initialize_talent_data(force_new=True)
            # Clear the cached hashes in the cache manager
            for key in list(self.cache_manager.cache.keys()):
                if (
                    key.count("_") == 2
                ):  # Assuming talent hash keys have two underscores
                    del self.cache_manager.cache[key]
            self.cache_manager.modified = True
            logger.info("Talent cache cleared.")

    def get_hash(self, hero_talent: str, class_talent: str, spec_talent: str) -> str:
        key = f"{hero_talent}_{class_talent}_{spec_talent}"
        cached_hash = self.cache_manager.get(key)
        if cached_hash is None or self.config.clear_cache:
            logger.debug(f"Generating new hash for {key}")
            talent_hash = generate_talent_hash(
                hero_talent,
                class_talent,
                spec_talent,
                self.config.spec_name.lower(),
                clear_cache=False,
                force_new=False,
            )
            self.cache_manager.set(key, talent_hash)
            return talent_hash
        logger.debug(f"Using cached hash for {key}")
        return cached_hash

    def get_hashes_batch(self, combinations: List[Tuple[str, str, str]]) -> List[str]:
        self.progress_tracker.set_progress_type("talent_hashing")
        hashes = []
        for i, combo in enumerate(combinations):
            hashes.append(self.get_hash(*combo))
            self.progress_tracker.update(f"{i+1}/{len(combinations)}")
        self.cache_manager.force_save()
        return hashes

    def preload_talents(self, talents: Dict[str, Dict[str, str]]):
        combinations = [
            (hero_talent, class_talent, spec_talent)
            for hero_talent in talents["hero_talents"].values()
            for class_talent in talents["class_talents"].values()
            for spec_talent in talents["spec_talents"].values()
        ]
        return self.get_hashes_batch(combinations)


class SimCContentGenerator:
    def __init__(self, config: SimConfig):
        self.config = config
        self.base_content = self._load_base_content()
        self.simc_params = {}
        self.profilesets = []
        self.supplemental_content = ""
        self.talents = config.talents
        self.is_multiple_simulation = False
        self.use_multi_threading = False
        logger.debug(f"SimCContentGenerator initialized with talents: {self.talents}")

    def set_multiple_simulation(self, is_multiple: bool):
        self.is_multiple_simulation = is_multiple
        logger.debug(f"Set multiple simulation: {is_multiple}")

    def set_multi_threading(self, use_multi_threading: bool):
        self.use_multi_threading = use_multi_threading
        logger.debug(f"Set multi-threading: {use_multi_threading}")

    def _load_base_content(self):
        base_file = FileHandler.join_path(self.config.apl_folder, "character.simc")
        content = self._merge_input_files(base_file)
        return self._remove_imports_comment(content)

    def _remove_imports_comment(self, content: str) -> str:
        lines = content.splitlines()
        return "\n".join(
            line for line in lines if not line.strip().lower().startswith("# imports")
        )

    def _merge_input_files(self, file_path: str, processed_files=None):
        if processed_files is None:
            processed_files = set()

        if file_path in processed_files:
            logger.warning(f"Circular reference detected: {file_path}")
            return ""

        processed_files.add(file_path)

        if not FileHandler.file_exists(file_path):
            logger.error(f"File not found: {file_path}")
            return ""

        base_dir = os.path.dirname(file_path)
        merged_content = []

        content = FileHandler.read_file(file_path)
        if content is None:
            return ""

        for line in content.splitlines():
            if line.strip().startswith("input="):
                input_file = line.split("=", 1)[1].strip()
                input_path = FileHandler.join_path(base_dir, input_file)
                merged_content.append(
                    self._merge_input_files(input_path, processed_files)
                )
                merged_content.append("\n")
            else:
                merged_content.append(line + "\n")

        return "".join(merged_content)

    def update_simc_param(self, key, value):
        self.simc_params[key] = value

    def update_talents(self, talents):
        self.simc_params["talents"] = talents

    def add_profileset(self, profileset):
        self.profilesets.append(profileset)

    def set_supplemental_content(self, content):
        self.supplemental_content = content

    def _generate_simc_config(self):
        config_params = [
            "iterations",
            "target_error",
            "desired_targets",
            "max_time",
            "json2",
            "html",
            "report_details",
            "optimize_expressions",
            "calculate_scale_factors",
            "scale_only",
            "normalize_scale_factors",
        ]
        config_content = "# SimC configuration\n"
        for param in config_params:
            if param in self.simc_params:
                config_content += f"{param}={self.simc_params[param]}\n"

        # Set thread options based on use_multi_threading flag
        if self.use_multi_threading:
            config_content += "threads=12\n"
            config_content += "profileset_work_threads=3\n"
        else:
            config_content += f"threads={self.config.threads}\n"
            config_content += (
                f"profileset_work_threads={self.config.profileset_work_threads}\n"
            )

        return config_content

    def _update_base_content(self):
        sections = {
            "simc configuration": self._generate_simc_config(),
            "character configuration": "",
            "buff configuration": "",
            "default consumables": "",
            "default gear": "",
        }
        updated_content = []
        current_section = ""

        for line in self.base_content.splitlines():
            line_lower = line.strip().lower()
            if line_lower.startswith("#") and line_lower[1:].strip() in sections:
                current_section = line_lower[1:].strip()
                if sections[current_section]:
                    updated_content.append(sections[current_section].strip())
                else:
                    updated_content.append(line)
            elif line_lower.startswith("talents="):
                if self.is_multiple_simulation:
                    updated_content.append("talents=")
                    logger.debug("Added empty talents for multiple simulation")
                else:
                    updated_content.append(f"talents={self.talents}")
                    logger.debug(f"Added talents: {self.talents}")
            elif not any(line.startswith(f"{param}=") for param in self.simc_params):
                updated_content.append(line)

        return "\n".join(updated_content)

    def generate_content(self):
        content = self._update_base_content()

        if self.profilesets:
            content += "\n\n# Profilesets\n"
            content += "\n".join(self.profilesets)

        if self.supplemental_content:
            content += "\n\n# Supplemental Content\n" + self.supplemental_content
        # Debug output
        if self.config.debug:
            debug_dir = "debug_output"
            FileHandler.ensure_directory(debug_dir)
            debug_file = FileHandler.join_path(debug_dir, "content_debug.simc")
            FileHandler.write_file(debug_file, content)

        return content


class Simulation(ABC):
    def __init__(
        self,
        config: SimConfig,
        talent_manager: TalentManager,
        cache_manager: CacheManager,
        progress_tracker: ProgressTracker,
    ):
        self.config = config
        self.talent_manager = talent_manager
        self.cache_manager = cache_manager
        self.progress_tracker = progress_tracker
        self.content_generator = SimCContentGenerator(config)
        logger.debug(f"Simulation initialized with talents: {self.config.talents}")

    @abstractmethod
    def run(self, params: SimulationParameters) -> Optional[Dict]:
        pass

    def execute_simulation(
        self, params: SimulationParameters, profiles: List[str], output_file: str
    ) -> Optional[str]:
        self._update_simulation_params(params)
        for profile in profiles:
            self.content_generator.add_profileset(profile)
        simc_content = self.content_generator.generate_content()
        logger.debug(f"Generated SimC content:\n{simc_content[:500]}")
        temp_input_file = self._create_temp_input_file(simc_content)
        if temp_input_file is None:
            return None

        try:
            return self._run_simc_process(temp_input_file, output_file, params.sim_id)
        finally:
            FileHandler.safe_delete(temp_input_file)

    def _update_simulation_params(self, params: SimulationParameters):
        self.content_generator.update_simc_param("iterations", params.iterations)
        self.content_generator.update_simc_param("target_error", params.target_error)
        self.content_generator.update_simc_param("fight_style", params.fight_style)
        self.content_generator.update_simc_param("max_time", params.time)
        if params.targets is not None:
            self.content_generator.update_simc_param("desired_targets", params.targets)
        if params.time:
            self.content_generator.update_simc_param("max_time", params.time)
        if self.config.json_output:
            json_output_file = self._generate_output_filename(params.sim_id, "json")
            self.content_generator.update_simc_param("json2", json_output_file)
        if self.config.html_output:
            html_output_file = self._generate_output_filename(params.sim_id, "html")
            self.content_generator.update_simc_param("html", html_output_file)
        self.content_generator.update_simc_param("threads", self.config.threads)
        self.content_generator.update_simc_param(
            "profileset_work_threads", self.config.profileset_work_threads
        )

    def _generate_output_filename(self, sim_id: str, extension: str) -> str:
        base_name = f"sim_output_{sim_id}" if self.config.timestamp else "sim_output"
        return FileHandler.join_path(
            self.config.report_folder, f"{base_name}.{extension}"
        )

    def _add_profiles(self, profiles: List[str]):
        for profile in profiles:
            self.content_generator.add_profileset(profile)

    def _create_temp_input_file(self, content: str) -> Optional[str]:
        temp_input_file = FileHandler.create_temp_file(content)
        if temp_input_file is None:
            logger.error("Failed to create temporary SimC input file.")
        return temp_input_file

    def _run_simc_process(
        self, input_file: str, output_file: str, sim_id: str
    ) -> Optional[str]:
        try:
            process = subprocess.Popen(
                [self.config.simc_path, input_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
            )

            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    logger.debug(line.strip())
                    self.progress_tracker.update(line.strip())

            rc = process.wait()
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.error(f"SimC stderr: {stderr_output}")

            if rc != 0:
                logger.error(f"Simulation failed with return code {rc}")
                return None

            logger.debug("Simulation completed successfully")

            # Use sim_id in the actual output file name
            actual_output_file = self._generate_output_filename(sim_id, "json")
            if FileHandler.check_output_file(actual_output_file):
                return actual_output_file

            # If the file doesn't exist, log an error and return None
            logger.error(f"Expected output file not found: {actual_output_file}")
            return None

        except Exception as e:
            logger.error(f"Error running simulation: {e}")
            return None

    def create_dataset(self, content: str, is_supplemental: bool = False) -> Dict:
        data = json.loads(content)
        return self._process_simulation_data(data, is_supplemental)

    @abstractmethod
    def _process_simulation_data(self, data: Dict, is_supplemental: bool) -> Dict:
        pass


class SingleSimulation(Simulation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.talent_combinations = {}

    def run(self, params: SimulationParameters) -> Optional[Dict]:
        logger.debug("Starting single simulation")
        label = (
            "DSlice"
            if params.fight_style == "DungeonSlice"
            else f"{params.targets}T_{params.time}s"
        )
        temp_output_file = FileHandler.join_path(
            self.config.report_folder,
            f"temp_single_sim_results_{label}_{params.sim_id}.json",
        )
        self.content_generator.set_multiple_simulation(False)
        self.content_generator.set_multi_threading(False)
        logger.debug(f"Single simulation talents: {self.content_generator.talents}")
        actual_output_file = self.execute_simulation(params, [], temp_output_file)
        if actual_output_file:
            content = FileHandler.read_file(actual_output_file)
            if content:
                return {label: self.create_dataset(content)}
        return None

    def _process_simulation_data(self, data: Dict, is_supplemental: bool) -> Dict:
        results = {}
        if "sim" in data and "players" in data["sim"] and data["sim"]["players"]:
            player = data["sim"]["players"][0]
            results["single_sim"] = {
                "dps": player["collected_data"]["dps"]["mean"],
                "talent_hash": self.config.talents,
            }
        return results


class MultipleSimulation(Simulation):

    def run(self, params: SimulationParameters) -> Optional[Dict]:
        logger.debug("Starting multiple simulations")
        label = (
            "DSlice"
            if params.fight_style == "DungeonSlice"
            else f"{params.targets}T_{params.time}s"
        )
        temp_output_file = FileHandler.join_path(
            self.config.report_folder,
            f"temp_sim_results_{label}_{params.sim_id}.json",
        )
        profiles = self.format_profiles()
        self.content_generator.set_multiple_simulation(True)
        self.content_generator.set_multi_threading(True)
        actual_output_file = self.execute_simulation(params, profiles, temp_output_file)
        if actual_output_file:
            content = FileHandler.read_file(actual_output_file)
            if content:
                return {label: self.create_dataset(content)}
        return None

    def format_profiles(self):
        profiles = []
        self.talent_combinations = {}  # New dictionary to store talent combinations
        talent_strings = self.config.talent_strings
        for hero_name, hero_talent in talent_strings["hero_talents"].items():
            for class_name, class_talent in talent_strings["class_talents"].items():
                for spec_name, spec_talent in talent_strings["spec_talents"].items():
                    profile_name = f"[{hero_name}] ({class_name}) {spec_name}"
                    profile = (
                        f'profileset."{profile_name}"="hero_talents={hero_talent}"\n'
                        f'profileset."{profile_name}"+="class_talents={class_talent}"\n'
                        f'profileset."{profile_name}"+="spec_talents={spec_talent}"\n\n'
                    )
                    profiles.append(profile)
                    # Store the talent combination separately
                    self.talent_combinations[profile_name] = (
                        f"{hero_name}|{class_name}|{spec_name}"
                    )
        return profiles

    def _process_simulation_data(self, data: Dict, is_supplemental: bool) -> Dict:
        results = {}
        if (
            "sim" in data
            and "profilesets" in data["sim"]
            and "results" in data["sim"]["profilesets"]
        ):
            for result in data["sim"]["profilesets"]["results"]:
                name = result["name"]
                dps = result["mean"]
                talent_combination = self.talent_combinations.get(name)
                if talent_combination:
                    hero_name, class_name, spec_name = talent_combination.split("|")
                    talent_hash = self.talent_manager.get_hash(
                        self.config.talent_strings["hero_talents"].get(hero_name, ""),
                        self.config.talent_strings["class_talents"].get(class_name, ""),
                        self.config.talent_strings["spec_talents"].get(spec_name, ""),
                    )
                    if talent_hash:
                        results[name] = {"dps": dps, "talent_hash": talent_hash}
        return results

    def _extract_names_from_index(self, index):
        hero_talents = list(self.config.talent_strings["hero_talents"].keys())
        class_talents = list(self.config.talent_strings["class_talents"].keys())
        spec_talents = list(self.config.talent_strings["spec_talents"].keys())

        hero_index = index % len(hero_talents)
        class_index = (index // len(hero_talents)) % len(class_talents)
        spec_index = index // (len(hero_talents) * len(class_talents))

        return (
            hero_talents[hero_index],
            class_talents[class_index],
            spec_talents[spec_index],
        )


class SupplementalSimulation(Simulation):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.supplemental_files = [
            "food_profilesets.simc",
            "consumable_profilesets.simc",
            "trinket_profilesets.simc",
            "embellishment_profilesets.simc",
            "gem_profilesets.simc",
            "enchant_profilesets_chest.simc",
            "enchant_profilesets_legs.simc",
            "enchant_profilesets_rings.simc",
            "enchant_profilesets_weapons.simc",
        ]

    def run(self, params: SimulationParameters) -> List[Optional[Dict]]:
        logger.info("Running supplemental profilesets simulations...")
        if not self.config.talents:
            raise ValueError(
                "Talents configuration is required for supplemental simulations."
            )

        sim_configs = [
            (params, f"{params.targets}T_{params.time}s"),
            (
                SimulationParameters(**{**params.__dict__, "targets": 5, "time": 120}),
                "5T_120s",
            ),
        ]

        results = []
        for i, supplemental_file in enumerate(self.supplemental_files):
            self.progress_tracker.current_simulation = (
                i + 2
            )  # +2 because we start at 1 and have already run the main sim
            result = self._run_single_supplemental(supplemental_file, sim_configs)
            if result:
                results.append(result)
            self.progress_tracker.start_new_simulation()

        return results

    def _run_single_supplemental(
        self,
        supplemental_file: str,
        sim_configs: List[Tuple[SimulationParameters, str]],
    ) -> Optional[Dict]:
        logger.debug(f"Starting supplemental simulation for {supplemental_file}")
        file_path = FileHandler.join_path(self.config.apl_folder, supplemental_file)
        if not FileHandler.file_exists(file_path):
            logger.warning(f"Supplemental file not found: {supplemental_file}")
            return None

        supplemental_content = FileHandler.read_file(file_path)
        if supplemental_content is None:
            logger.error(f"Failed to read supplemental file: {supplemental_file}")
            return None

        results = {os.path.splitext(supplemental_file)[0]: {}}

        for params, label in sim_configs:
            result = self._run_supplemental_with_params(
                params, supplemental_file, supplemental_content
            )
            if result:
                results[os.path.splitext(supplemental_file)[0]][label] = result
            self.progress_tracker.start_new_simulation()

        return results

    def _run_supplemental_with_params(
        self,
        params: SimulationParameters,
        supplemental_file: str,
        supplemental_content: str,
    ) -> Optional[Dict]:
        self.content_generator = SimCContentGenerator(self.config)
        self.content_generator.set_multiple_simulation(False)

        profileset_count = self._count_profilesets(supplemental_content)
        use_multi_threading = profileset_count > 10
        self.content_generator.set_multi_threading(use_multi_threading)

        if use_multi_threading:
            logger.info(
                f"Setting multi-threading for {supplemental_file} due to high number of profilesets ({profileset_count})"
            )

        supplemental_params = self._set_supplemental_params(params)
        self._update_simulation_params(supplemental_params)
        self.content_generator.update_talents(self.config.talents)
        self.content_generator.add_profileset(supplemental_content)

        sim_id = (
            f"{supplemental_params.sim_id}_{os.path.splitext(supplemental_file)[0]}"
            if self.config.timestamp
            else "supplemental"
        )
        output_file = self._generate_output_filename(sim_id, "json")

        actual_output_file = self.execute_simulation(
            supplemental_params, [], output_file
        )
        if actual_output_file:
            content = FileHandler.read_file(actual_output_file)
            if content:
                return self.create_dataset(content, supplemental_file)
        return None

    def _set_supplemental_params(
        self, params: SimulationParameters
    ) -> SimulationParameters:
        return SimulationParameters(
            iterations=10000,
            target_error=0.2,
            targets=params.targets,
            time=params.time,
            fight_style=params.fight_style,
            sim_id=params.sim_id,
        )

    @staticmethod
    def _count_profilesets(content: str) -> int:
        return content.count("profileset.")

    def _process_simulation_data(self, data: Dict, supplemental_file: str) -> Dict:
        return {
            result["name"]: {"dps": result["mean"], "name": result["name"]}
            for result in data.get("sim", {}).get("profilesets", {}).get("results", [])
        }


class SimulationRunner:
    def __init__(
        self,
        config: SimConfig,
        talent_manager: TalentManager,
        cache_manager: CacheManager,
        progress_tracker: ProgressTracker,
    ):
        self.config = config
        self.talent_manager = talent_manager
        self.cache_manager = cache_manager
        self.progress_tracker = progress_tracker

        self.single_simulation = SingleSimulation(
            config, talent_manager, cache_manager, progress_tracker
        )
        self.multiple_simulation = MultipleSimulation(
            config, talent_manager, cache_manager, progress_tracker
        )
        self.supplemental_simulation = SupplementalSimulation(
            config, talent_manager, cache_manager, progress_tracker
        )

        self._set_total_simulations()

    def _set_total_simulations(self):
        total = 1 if self.config.single_sim else len(self.config.parse_sim_parameters())
        if self.config.supplemental_profilesets:
            total += len(self.supplemental_simulation.supplemental_files)
        self.progress_tracker.set_total_simulations(total)

    def run_simulations(self):
        logger.debug("Starting simulations")
        self.talent_manager.preload_talents(self.config.talent_strings)

        if self.config.supplemental_profilesets and not self.config.talents:
            raise ValueError(
                "Talents configuration is required for supplemental simulations."
            )

        sim_params = self.config.parse_sim_parameters()
        results = []

        if self.config.single_sim:
            results.append(self._run_single_simulation(sim_params[0]))
        else:
            results.extend(self._run_multiple_simulations(sim_params))

        if self.config.supplemental_profilesets:
            supplemental_results = self._run_supplemental_simulations(sim_params[0])
            results.extend(supplemental_results)

        logger.debug("All simulations completed")
        return results

    def _run_single_simulation(self, params: SimulationParameters) -> Optional[Dict]:
        logger.debug("Running single simulation")
        return self.single_simulation.run(params)

    def _run_multiple_simulations(
        self, sim_params: List[SimulationParameters]
    ) -> List[Optional[Dict]]:
        logger.debug("Running multiple simulations")
        results = {}
        for params in sim_params:
            result = self.multiple_simulation.run(params)
            if result:
                results.update(result)
            self.progress_tracker.start_new_simulation()
        return [results]

    def _run_supplemental_simulations(
        self, params: SimulationParameters
    ) -> List[Optional[Dict]]:
        return self.supplemental_simulation.run(params)


class APLCombiner:
    def __init__(self, config: SimConfig):
        self.config = config
        self.base_dir = config.apl_folder
        self.simc_path = config.simc_path

    def combine_apl(self):
        if not self.config.generate_combined_apl:
            return

        main_file = FileHandler.join_path(self.base_dir, "character.simc")
        temp_file = FileHandler.join_path(self.base_dir, "temp_combined.simc")
        output_file = FileHandler.join_path(self.base_dir, "full_character.simc")

        combined_content = self._process_file(main_file)

        if FileHandler.write_file(temp_file, combined_content):
            self._compile_with_simc(temp_file, output_file)
        else:
            logger.error("Failed to save temporary combined APL")

    def _process_file(self, file_path: str) -> str:
        content = FileHandler.read_file(file_path)
        if content is None:
            return ""

        processed_content = []
        for line in content.splitlines():
            if line.strip().startswith("input="):
                input_file = line.split("=", 1)[1].strip()
                input_path = FileHandler.join_path(self.base_dir, input_file)
                processed_content.extend(["\n", self._process_file(input_path), "\n"])
            elif not line.lower().strip().startswith("# imports"):
                processed_content.append(line)

        return "\n".join(processed_content)

    def _compile_with_simc(self, input_file: str, output_file: str):
        try:
            result = subprocess.run(
                [self.simc_path, input_file, f"save={output_file}"],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"Successfully compiled and saved to {output_file}")
            logger.debug(f"SimC output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Error running SimC: {e}")
            logger.error(f"SimC stderr: {e.stderr}")
        except FileNotFoundError:
            logger.error(f"Error: SimC executable not found at {self.simc_path}")
        finally:
            FileHandler.safe_delete(input_file)
            logger.debug(f"Temporary file {input_file} deleted")


def parse_profiles_simc(profiles_path, talent_manager):
    if not FileHandler.file_exists(profiles_path):
        logger.error(f"Profiles file not found: {profiles_path}")
        return None, None
    content = FileHandler.read_file(profiles_path)
    if content is None:
        return None, None

    talents = {
        category: {} for category in ["hero_talents", "class_talents", "spec_talents"]
    }
    talent_strings = {
        category: {} for category in ["hero_talents", "class_talents", "spec_talents"]
    }
    sections = re.split(
        r"#\s*(Hero tree variants|Class tree variants|Spec tree variants)", content
    )

    if len(sections) != 7:
        logger.error(
            f"Unexpected number of sections in profile_templates.simc: {len(sections)}"
        )
        return None, None

    for i, section_name in enumerate(["hero_talents", "class_talents", "spec_talents"]):
        section_content = sections[i * 2 + 2]
        talent_defs = re.findall(r'\$\(([\w_]+)\)="([^"]+)"', section_content)
        if not talent_defs:
            logger.error(f"No talent definitions found for {section_name}")
            return None, None
        talents[section_name] = dict(talent_defs)
        talent_strings[section_name] = {name: string for name, string in talent_defs}

    return talents, talent_strings


def run_create_profiles(config: SimConfig):
    create_profiles_script = FileHandler.join_path(
        os.path.dirname(__file__), "create_profiles.py"
    )
    subprocess.run(
        [sys.executable, create_profiles_script, config.config_path], check=True
    )


def cleanup_raw_output(config: SimConfig):
    raw_output_pattern = FileHandler.join_path(
        config.report_folder, "sim_output_*.json"
    )
    deleted_files = 0
    for file in glob.glob(raw_output_pattern):
        if FileHandler.safe_delete(file):
            deleted_files += 1
    logger.info(f"Cleaned up {deleted_files} raw output file(s).")


def run_compare_reports(config_path: str):
    compare_reports_script = FileHandler.join_path(
        os.path.dirname(__file__), "compare_reports.py"
    )
    subprocess.run([sys.executable, compare_reports_script, config_path], check=True)


def main(config_path: str):
    try:
        sim_config = SimConfig.from_file(config_path)
    except (FileNotFoundError, RuntimeError) as e:
        logger.error(str(e))
        return

    # Ensure necessary directories exist
    FileHandler.ensure_directory(sim_config.apl_folder)
    FileHandler.ensure_directory(sim_config.report_folder)

    with CacheManager(sim_config) as cache_manager:
        progress_tracker = ProgressTracker(total_simulations=1)
        talent_manager = TalentManager(sim_config, cache_manager, progress_tracker)

        if sim_config.clear_cache:
            run_create_profiles(sim_config)
            cache_manager.clear()
            talent_manager.clear_cache_if_needed()

        profiles_path = FileHandler.join_path(
            sim_config.apl_folder, "profile_templates.simc"
        )
        talents, talent_strings = parse_profiles_simc(profiles_path, talent_manager)
        if talents is None or talent_strings is None:
            logger.error("Failed to parse talent strings. Exiting.")
            return

        sim_config.talent_strings = talent_strings

        simulation_runner = SimulationRunner(
            sim_config, talent_manager, cache_manager, progress_tracker
        )

        results = simulation_runner.run_simulations()

        # Process and save results
        output_file = FileHandler.join_path(
            sim_config.report_folder, "simulation_results.json"
        )

        # Merge all results into a single dictionary
        merged_results = {}
        for result in results:
            if isinstance(result, dict):
                merged_results.update(result)

        FileHandler.write_file(output_file, json.dumps(merged_results, indent=2))

        logger.info(f"Simulation results saved to {output_file}")

        # Cleanup: Delete raw JSON output files
        cleanup_raw_output(sim_config)

        # Run combine.py
        if sim_config.generate_combined_apl:
            apl_combiner = APLCombiner(sim_config)
            apl_combiner.combine_apl()

        # Run compare_reports.py
        if sim_config.generate_website:
            run_compare_reports(config_path)

    logger.info("All simulations, post-processing, and report generation completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SimulationCraft profiles")
    parser.add_argument("config", help="Path to configuration file")
    args = parser.parse_args()
    main(args.config)
