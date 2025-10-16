function mem = load_mem(mem_fn)

fields = {'lo_dens_flux', 'hi_dens_flux', 'lo_dens_speed', 'hi_dens_speed'};
mem = load_nc(mem_fn);
all_fields = fieldnames(mem);

for fi = 1:length(all_fields)
    mem.(all_fields{fi}) = double(mem.(all_fields{fi}));
end

mem.times = datenum(mem.year, mem.month, mem.day, mem.hour, mem.minute, 0);

nmonth = length(unique(mem.month));
nhr = length(unique(mem.hour));

shape = [nhr, nmonth, 12, 19];
for fi = 1:length(fields)
    mem.(fields{fi}) = reshape(mem.(fields{fi}), shape);
    mem.(fields{fi}) = cat(3, mem.(fields{fi}), mem.(fields{fi})(:, :, 1, :));
    mem.(fields{fi}) = cat(2, mem.(fields{fi})(:, end, :, :), ...
        mem.(fields{fi}), mem.(fields{fi})(:, 1, :, :));

end
mem.lon = [mem.lon; 360];
mem.times = reshape(mem.times, [nhr, nmonth]);
mem.times = [mem.times(:, 1) - 31, mem.times, mem.times(:, end) + 31];

mem.month = unique(mem.month);
mem.hour = unique(mem.hour);

