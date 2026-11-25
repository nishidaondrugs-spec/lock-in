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

POKEMON IN THE ARENA (v2.0)
- Finishing tasks, focus sessions, clearing your Top 3 and beating bosses can bring a wild Pokemon.
  Click "Catch" (or the Pokemon) to throw a ball - 3 tries before it flees.
- Rare forms: shiny (about 1 in 40) and shadow (about 1 in 60). Legendaries are very rare.
- Open the Dex, tap a Pokemon to make it your partner. It fights beside the knight,
  or switch "Fight as" to Partner to let it lead the battle.
- Sprites load from the PokeAPI sprites repo on GitHub, so they need internet. Pokemon art belongs
  to Nintendo / Game Freak - personal use only.

CLAUDE CONNECTOR (v2.1)
Lets the Claude desktop app read your Lock In plan and add / move / complete things for you.
- Setup: install_autostart.bat does it automatically. Or run connect_claude.bat. Then FULLY quit and reopen Claude.
- Try: "what's on my Lock In this week?", "find me a free 90 minutes on Saturday", "pencil in Lars lectures Sat 10am".
- It only talks to Lock In on THIS computer (127.0.0.1) using a private key stored in %APPDATA%\LockIn\agent.token.
  Nothing is sent to the internet by the connector. Claude only sees what you ask it about in a chat.
- Lock In has to be running. If the window is closed when Claude adds something, Lock In opens it to apply the change.
- Manual setup / Claude Code:  claude mcp add lockin -- python "%LOCALAPPDATA%\LockIn\app\mcp_lockin.py"

NO MORE OVERWRITING (v2.2)
Lock In now notices when your plan was changed from somewhere else (another window, Claude through the connector,
a restored backup) and picks the change up within a few seconds instead of overwriting it. If you edit something at
the same moment, your edit and the other change are merged item by item.

AUTO-SLOT + NOTES (v2.3)
- Inbox > "Auto-slot into my free time": Lock In finds gaps in your week (9am-9pm, 15 min clear of other events,
  max 3 a day), shows you the plan, and pencils the ones you keep. Nothing is final until you confirm.
- Notes (left menu): a scratchpad with autosave. Start a line with [] and press "Turn [] lines into Inbox tasks".

CONTENT + EP STUDIO (v2.4)
- Content view: "New episode" makes "EP. N turning my followers into cards" with a 7-step checklist (follower, cut-out,
  record, CapCut edit, accept card, post, log after 24h). Ticking "Post it" moves it to Posted.
- "Reels posted this week x/6" counter (also on Today). Set your goal and the next EP number in Settings.
- "Open EP Studio" button: in Settings put EP Studio's web address (http://...) or the file path on this computer.
