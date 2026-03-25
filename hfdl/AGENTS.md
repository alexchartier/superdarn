# Agent Notes

- Server access is via `ssh superdarn@tuvalu`.
- SuperDARN website deployed files are under `tuvalu:/project/superdarn/www` with web root at `tuvalu:/project/superdarn/www/htdocs`.
- Server login shell is `tcsh` (reported by `echo $SHELL`).
- Use `/software/python-3.11.4/bin/python3` on the server (`python3` is aliased there).
- For multi-step remote work, prefer a persistent PTY session:
  `ssh superdarn@tuvalu`, then from there `ssh wal`.
- Avoid stacking nested non-interactive SSH commands through `tuvalu` when possible.
  `tcsh` quoting and profile startup can waste time and break commands.
- If a one-shot remote copy is needed, simple streaming commands are fine, e.g.
  `ssh superdarn@tuvalu 'ssh wal "cat /path/to/file"' > /local/path`.
- For Borealis process control on Wallops, use the interactive `wal` shell rather than
  trying to drive `steamed_hams.py`, `ps`, or `pgrep` through heavily escaped nested commands.
- I have read access on the server; ask for explicit permission before changing any code on the server.
- Explicit permission granted to SSH to the server for read-only checks.
- Explicit permission granted to install software under `/project/superdarn/software/` on the server.
- Explicit permission granted to modify server code during this session.
- Keep USRP bring-up conservative (no bulk power cycling).
- Keep generated plots for this repo under `plots/`.
- When reporting a plot path to the user, include the repo-relative path such as `plots/foo.png`.
