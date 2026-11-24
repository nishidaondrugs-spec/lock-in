# Releasing an update
Lock In checks `version.txt` and `lockin.zip` in this repo's root (via raw.githubusercontent.com).
To release: change the number in `version.txt` (and inside the zip), rebuild `lockin.zip` (a `lockin/` folder holding app.py, static/, version.txt, ...), commit, push.
Installed copies update themselves within a few hours (or via Settings > Check for updates). User data is never touched.
