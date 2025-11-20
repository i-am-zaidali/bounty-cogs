# NoPollMessage

A Red-DiscordBot cog that suppresses poll messages when a poll ends and optionally sends a custom message.

## Features
- Suppress default poll end messages.
- Send customizable messages when polls end.

## Usage
- Base Command: `[p]nopollmsg`
- Enable/Disable poll end messages deletion: `[p]nopollmsg enable/disable`
- Set a custom poll end message: `[p]nopollmsg custommessage [message]` (running without arguments sends current custom message)
- Remove custom message: `[p]nopollmsg custommessage clear`
- Placeholders for custom messages:
  - `{poll_question}`: The question of the poll.
  - `{poll_url}`: URL to the poll.
  - `{winning_option}`: The option that won the poll.
  - `{winning_votes}`: Number of votes for the winning option.
  - `{total_votes}`: Total number of votes cast in the poll.
- Example custom message:
  ```
  The poll for [{poll_question}]({poll_url}) has ended! The winning option was: `{winning_option}` with `{winning_votes}` votes out of {total_votes} votes.
  ```