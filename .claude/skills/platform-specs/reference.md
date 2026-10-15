# Platform specs: sources and conflicts

Checked 2026-10-15. Every figure below comes from third-party guides and tool sites, not from the platforms' own help pages. To upgrade a figure, find the official help page, put its URL here and change the date.

## Instagram
- Caption: 2,200 characters (most guides). About 125 show in the feed before "more".
- Hashtags: most guides say 30 per post, counting the caption and comments together. One guide (socialk.it) says the cap fell to 5 from December 2025 and that older accounts may keep 30. **Unconfirmed.** Several guides advise 3-5 relevant ones whatever the cap.
- Sources: sendible.com/insights/instagram-character-limit, growthscribe.com/instagram-caption-character-limit, socialk.it/en/tools/instagram-character-counter, howmanywords.app/blog/instagram-character-limits.

## LinkedIn
- Post: 3,000 characters, counting spaces, line breaks, hashtags and emoji. Links count at full length.
- Fold: about 140 characters on mobile and 210 on desktop before "see more" (sources differ slightly).
- Hashtags: guides suggest 3-5. The team's own rule of at most 3 comes from `personas/content.md`, not from LinkedIn.
- Not agreed: comment limit (1,250 or 1,500) and DM limit (1,900 to 8,000).
- Sources: authoredup.com/blog/linkedin-character-limit, eden.so/blog/linkedin-character-limits, unil.ink/ua/blog/linkedin-character-limits-2026.

## X
- 280 characters on free accounts. Premium accounts can post up to 25,000, but the feed shows them collapsed.
- Any link counts as 23 characters, whatever its length.
- Sources: socialk.it/en/tools/x-character-counter, help.metricool.com/en/article/character-limit-for-each-social-network-4ivf8t/.

## Facebook
- **Sources conflict:** 63,206 (several guides), 16,192 (Metricool), 5,000 for pages and groups (Buffer). Don't quote a number. Keep posts short and put the point first.
- Sources: help.metricool.com/en/article/character-limit-for-each-social-network-4ivf8t/, buffer.helpscoutdocs.com/article/588-character-limits-for-each-social-network.

## TikTok
- Caption: **2,200 or 4,000, sources conflict** (one guide gives both).
- Visible before "more": between 80 and 125 characters, depending on the guide.
- Maximum video length: not found in any source. Unchecked.
- Sources: wordcountertool.net/character-limits/tiktok, howmanywords.app/blog/tiktok-character-limits.

## Video (HeyGen avatar)
- 50 words is the cap in this repo (`MAX_VIDEO_WORDS` in `tools.py`). HeyGen has no maximum-duration setting, so word count is the only limit. About 0.5 seconds per word gives about 25 seconds.
- Every video renders at 720p.
