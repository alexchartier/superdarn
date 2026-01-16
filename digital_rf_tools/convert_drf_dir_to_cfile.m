
function convert_drf_dir_to_cfile(directory, outfile)
% convert_drf_dir_to_cfile(directory, outfile)
%
% Reads ALL DigitalRF .h5 files in the given directory,
% extracts the compound IQ dataset /rf_data,
% converts to complex float32 IQ,
% concatenates all segments in chronological order,
% and writes them into ONE combined .cfile.
%
% Example:
% convert_drf_dir_to_cfile('C:\data\cha\2025-12-12T16-00-00\', 'combined.cfile')

    % Find all .h5 files
    files = dir(fullfile(directory, '*.h5'));
    if isempty(files)
        error('No .h5 files found in %s', directory);
    end

    % Sort by filename (DigitalRF naming is time-ordered)
    [~, idx] = sort({files.name});
    files = files(idx);

    fprintf("Found %d HDF5 files.\n", numel(files));

    % Prepare output
    fid_out = fopen(outfile, 'wb');
    if fid_out < 0
        error('Could not open output file: %s', outfile);
    end

    % Process each file
    for k = 1:numel(files)
        inname = fullfile(directory, files(k).name);
        fprintf("Reading %s ...\n", inname);

        % Read DigitalRF compound dataset
        raw = h5read(inname, '/rf_data');   % raw.r and raw.i fields

        % DigitalRF stores 1xN — flatten to Nx1
        I = double(raw.r(:)) / 32768;   % scale int16 → float [-1,1]
        Q = double(raw.i(:)) / 32768;

        % Combine to complex
        x = complex(I, Q);

        % Interleave as CF32: I0 Q0 I1 Q1 ...
        iq = zeros(2*length(x), 1, 'single');
        iq(1:2:end) = real(x);
        iq(2:2:end) = imag(x);

        % Append to output file
        fwrite(fid_out, iq, 'single');
    end

    fclose(fid_out);
    fprintf("Combined CF32 IQ written to: %s\n", outfile);
end
