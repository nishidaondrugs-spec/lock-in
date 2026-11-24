LOCK IN
=======
INSTALL (or UPDATE - same thing, your data is safe):
  1. Unzip this folder anywhere (Downloads is fine).
  2. Double-click  install_autostart.bat
     - copies the app to  %LOCALAPPDATA%\LockIn\app   (you can delete the unzipped folder afterwards)
     - your events live in  %APPDATA%\LockIn           (never touched by installs, updates or deletes)
     - opens Lock In at login + puts a "Lock In" shortcut on your Desktop
  Needs Python and Microsoft Edge or Chrome. No pip installs.

AUTO-UPDATES (optional): Settings > "Update address". Point it at the web folder that holds version.txt and lockin.zip.
  With "Install updates automatically" on, Lock In checks every few hours, installs the new version and restarts itself.
  Settings > Check for updates does it on demand. Settings > Backup / Restore a backup copies your data in and out.

Day to day: press N to drop anything in. Close the window any time - reminders keep working in the background and the
window pops back open when a reminder fires or when you wake the laptop.
stop_lockin.bat quits it. remove_autostart.bat stops it opening at login (data is kept).

QUICK-ADD EXAMPLES (top bar, Enter)
  EVERY WEEK TUESDAY S&C Hallam 4.15pm to 5.15pm
  every other week thursday physio 6-7pm      every 3 weeks fri review 5pm
  every mon and wed gym 7pm   daily standup 9am   every weekday commute 8:30
  fri 3pm call X #jobs r30    film ep 22 sat 3pm?   (? = pencil it in, confirm later)
Click a repeating event to delete just that day, that day and all after, or the whole series; pick an emoji + colour there too.
