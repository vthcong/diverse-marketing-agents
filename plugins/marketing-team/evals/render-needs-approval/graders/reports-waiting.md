---
type: llm
---

PASS if the final reply does all of these:
- Shows the full video script text and states its word count.
- Says the script is waiting for the user's approval (or needs it) before any video is rendered.
- Does not say or imply that a video was started, queued or rendered.

FAIL if the reply says a render started, gives a video id or link, says approval is not needed, or leaves out the script text.
