import os
import subprocess
import argparse
import configparser
import sys

def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' does not exist.")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)
    return config

def combine_and_compile_files(config):
    apl_folder = config['General']['apl_folder']
    main_file = os.path.join(apl_folder, 'character.simc')
    output_file = os.path.join(apl_folder, 'full_character.simc')
    simc_path = config['General']['simc']
    base_dir = os.path.dirname(main_file)

    def process_file(file_path):
        content = []
        with open(file_path, 'r') as infile:
            for line in infile:
                if line.startswith('input='):
                    filename = line.split('=')[1].strip()
                    full_path = os.path.join(base_dir, filename)
                    content.extend(['\n'] + process_file(full_path) + ['\n'])
                elif line.lower().startswith('# imports'):
                    continue
                else:
                    content.append(line)
        return content

    combined_content = process_file(main_file)

    temp_file = os.path.join(apl_folder, 'temp_combined.simc')
    with open(temp_file, 'w') as outfile:
        outfile.writelines(combined_content)

    try:
        subprocess.run([simc_path, temp_file, f'save={output_file}'], check=True)
        print(f"Successfully compiled and saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error running simc: {e}")
    except FileNotFoundError:
        print(f"Error: simc executable not found at {simc_path}")

    os.remove(temp_file)

def main():
    parser = argparse.ArgumentParser(description='Combine and compile SimulationCraft files.')
    parser.add_argument('config', help='Path to the configuration file')

    args = parser.parse_args()

    config = load_config(args.config)
    combine_and_compile_files(config)

if __name__ == "__main__":
    main()