# WorkBuddy Electron paste helper (pattern)

```bash
pbcopy < task-zh.txt
WB_PID=$(pgrep -f '/Applications/WorkBuddy.app/Contents/MacOS/Electron$' | head -1)
osascript <<APPLESCRIPT
tell application "WorkBuddy" to activate
delay 0.5
tell application "System Events"
  set wb to first process whose unix id is $WB_PID
  set frontmost of wb to true
  tell wb
    keystroke "a" using command down
    delay 0.15
    key code 51
    delay 0.25
    try
      click menu item "粘贴" of menu "编辑" of menu bar 1
    on error
      keystroke "v" using command down
    end try
  end tell
end tell
APPLESCRIPT
```

Then AX-check unique task markers and Send enabled.
