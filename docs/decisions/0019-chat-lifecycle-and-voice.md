# 0019. Chat lifecycle, edits, voice and video notes

English · [Русский](../ru/decisions/0019-chat-lifecycle-and-voice.md)

## Context
Every co-op quest gets a group chat (ADR 0007, US-18), and nothing ever removes it: the chat list fills with chats of quests long over. The owner (2026-10-24) also wants message editing, voice messages and round video notes ("кружочки") as in other messengers. Video calls were weighed and dropped: they need a TURN server and, for groups, a media server, and calls in messengers are restricted in Russia.

## Decision
- **Delete for me.** `DELETE /conversations/{id}` hides a chat for the caller with all its messages so far and marks it read (`chat.members.hidden_at`); the other members keep it. A newer message brings the chat back with only what came after.
- **Co-op chats end.** A co-op chat is deleted for everyone, with its messages and files, 30 days after its quest is over (`expires_at` of the co-op). The chat shows the date once the quest is over (`Conversation.deletes_at`). Direct chats stay until deleted.
- **Editing.** The author can edit a text message within 24 hours; the message shows "изменено" and members get the change over realtime.
- **Voice messages** up to 5 minutes and **video notes** up to 60 seconds go through the media upload of photos (presigned PUT to the private S3 bucket in Russia, then a worker job). The worker re-encodes with ffmpeg: voice to Opus 32 kbit/s in Ogg (about 240 KB a minute), video notes to H.264 480x480 at about 600 kbit/s with AAC sound in MP4 (up to about 5 MB). The original upload is deleted after the re-encode; metadata (location, device) is stripped as for photos.
- **Video notes live 30 days**, in any chat; the message then says the video note has expired. Voice messages live as long as their chat.

## Consequences
The chat list stays short, and storage grows slowly: at 1000 active users with 5 voice messages and 2 video notes a day, about 300 GB are kept at a time (about 9 EUR a month at Beget). Re-encoding video takes the worker's CPU: 4 vCPU handle thousands of video notes a day; beyond that the worker moves to its own machine. ffmpeg is added to the backend image. Voice and video are personal data stored in Russia like photos; the privacy policy names them and their retention. No calls: friends call in their usual messenger.
