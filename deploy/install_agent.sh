#!/bin/zsh
# Install a launchd agent that runs run_online.sh at login and restarts it if it stops
# (engine crash, tunnel drop, Mac wake from sleep). Logs: ~/Library/Logs/myvoice.log
# Remove with: launchctl bootout gui/$UID/com.ikppramesh.myvoice && rm ~/Library/LaunchAgents/com.ikppramesh.myvoice.plist
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=com.ikppramesh.myvoice
PLIST=~/Library/LaunchAgents/$LABEL.plist
mkdir -p ~/Library/LaunchAgents ~/Library/Logs
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$ROOT/run_online.sh</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>15</integer>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/myvoice.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/myvoice.log</string>
</dict>
</plist>
EOF
launchctl bootout gui/$UID/$LABEL 2>/dev/null
launchctl bootstrap gui/$UID "$PLIST"
echo "Installed $LABEL — logs: tail -f ~/Library/Logs/myvoice.log"
