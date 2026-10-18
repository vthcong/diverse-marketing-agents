---
description: Turn chosen copy into a short script written for the ear, within the 50-word video cap, and check the word count
when_to_use: Use when adapting a caption or post into a spoken avatar-video script, or revising a video script
---

# Spoken script

Written copy and spoken copy are different. Rewrite for the ear.

## Length
**50 words or fewer**, about 25 seconds. Saving a longer script is rejected. Count the words before you save. If you can run commands, use the helper:

```
/opt/miniconda3/envs/langchain/bin/python ${CLAUDE_SKILL_DIR}/count_words.py "your script here"
```

It prints the word count and flags anything an avatar can't speak (hashtags, emoji, URLs, markdown). It exits with an error if the script is over the cap. If you can't run commands, count the words yourself and leave headroom.

## Write it
- **Open strong:** a hook of about 8 words or fewer, lifted from the chosen copy.
- **Short sentences,** roughly 12 words each. Contractions are fine. Say "you", not "customers".
- **One idea and one call to action.** Cut everything else, including the second and third benefits.
- **Numbers as you'd say them:** "twenty percent", "the fifteenth of October". Write a name or acronym the way it should sound.
- **No** hashtags, emoji, URLs, markdown, brackets or stage directions.
- **A spoken call to action:** "Come find us", "Search for the brand", not a web address.

## Check it
1. Read it aloud. If you stumble, rewrite that line.
2. Run the count.
3. Confirm every claim is in the chosen copy (see `fact-grounding`). The script adds nothing new.

## Then
Show the user the script and its approximate length, and ask for a go-ahead before spending credits. Approval of an older script doesn't carry over to a revised one.
