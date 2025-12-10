import h5py
import sys
import os
import bz2

def copy_first_record(infile, outfile):
    with h5py.File(infile, 'r') as f:
        records = sorted(list(f.keys()))
        first_rec = f[records[0]]
        with h5py.File(outfile, 'w') as ofile:
            group = ofile.create_group(records[0])
            f.copy(first_rec, group)

def decompress_bz2_file(bz2_filename, decompressed_filename):
    with bz2.BZ2File(bz2_filename, 'rb') as bz2_file:
        with open(decompressed_filename, 'wb') as decompressed_file:
            decompressed_file.write(bz2_file.read())

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python script.py <input_filename> <output_filename>")
        sys.exit(1)
    
    input_filename = sys.argv[1]
    output_filename = sys.argv[2]
    
    # Check if the input file is BZ2-compressed
    if input_filename.endswith('.bz2'):
        decompressed_filename = input_filename[:-4]  # Remove the '.bz2' extension
        decompress_bz2_file(input_filename, decompressed_filename)
        input_filename = decompressed_filename  # Use the decompressed file for further processing
    
    copy_first_record(input_filename, output_filename)
    
    # If we decompressed a file, optionally clean up the decompressed file
    if input_filename.endswith('.hdf5') and os.path.exists(input_filename) and input_filename != sys.argv[1]:
        os.remove(input_filename)
