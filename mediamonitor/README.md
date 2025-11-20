# MediaMonitor

## Purpose
MediaMonitor scans messages and attachments and flags or acts on attachments that match configured rules (filename regex, file size limit, or blacklisted file types).

## Features
- Monitor specific channels for attachments.
- Flag attachments by:
  - Filename regex (admin-provided).
  - Maximum file size.
  - Blacklisted file extensions/types (e.g., .exe, .zip).
- Emit violations and take configured actions (log, delete message, warn/mute, etc.).
- Safe regex execution in a separate process with timeouts to mitigate ReDoS / catastrophic backtracking.

## Main commands (overview)
- `[p]mediamonitor filenameregex <regex|none>`
  - Set or clear the filename regex used to flag attachments.
- `[p]mediamonitor filesizelimit <bytes|none>`
  - Set a maximum file size in bytes; attachments larger than this are considered a violation.
- `[p]mediamonitor filetypes add|remove|list <ext>`
  - Configure blacklisted file extensions/types (no leading `.` required).
- `[p]mediamonitor monitoringchannels add|remove|list <#channel>`
  - Configure which channels are monitored for attachments.
- `[p]mediamonitor logchannel <#channel|none>`
  - Set or clear the channel where violations are logged.
- `[p]mediamonitor deleteonviolation <true|false>`
  - Toggle automatic deletion of violating messages (bot requires Manage Messages permission).
- Additional admin options:
  - See `[p]help MediaMonitor` for controls for whitelisting users/channels/roles, action thresholds etc.

Example quick setup (replace [p] with your bot prefix)
- Set filename regex:
  - `[p]mediamonitor filenameregex (?i)\.(exe|zip|bat)$`
- Blacklist filetypes:
  - `[p]mediamonitor filetypes add exe zip bat`
- Monitor a channel:
  - `[p]mediamonitor monitoringchannels add #attachments`
- Set log channel:
  - `[p]mediamonitor logchannel #mod-log`
- Enable deletion on violation:
  - `[p]mediamonitor deleteonviolation true`
