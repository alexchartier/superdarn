import os


def search_directories(directory_path, log_file):
    for root, dirs, files in os.walk(directory_path):
        for subdir in dirs:
            subdir_path = os.path.join(root, subdir)
            if os.path.isdir(subdir_path):
                subdir_size = get_directory_size(subdir_path)
                if subdir_size < 100 * 1024:  # Convert 100kB to bytes
                    log_file.write(subdir_path + '\n')


def get_directory_size(directory_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    return total_size


# Directory to search
directory_to_search = '/project/superdarn/data/meteorwind/'

# Log file path
log_file_path = '/project/superdarn/logs/empty_dir_results.log'

# Open the log file in 'append' mode
with open(log_file_path, 'a') as log_file:
    # Call the search function
    search_directories(directory_to_search, log_file)
