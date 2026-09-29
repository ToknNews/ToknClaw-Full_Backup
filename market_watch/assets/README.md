# Original Tokn brand assets

These are unmodified copies of assets from the owner's public repository:

- Repository: https://github.com/ToknNews/ToknNews-Full_Backup
- Commit: `70fcd4b37147acbb34294b5086d597d7d04bf2ce`
- Original directory: `frontend/assets/img/`
- Palette source: `frontend/assets/css/tokn.css` and `landing.css` at the same commit. Electric blue is `rgba(45,115,255,...)` / `#2D73FF`; pale text is `#CCECFF`; the site uses black and dark navy surfaces.

| File | Use | SHA-256 |
| --- | --- | --- |
| `Tokn_Favicon.png` | Discord sender avatar, author icon and alert/follow-up thumbnail | `a4ea8c2083f56dd55a00c0e08e6233679ed7a0c271931c5f0bf4db0205231adb` |
| `Tokn_Logo_Main_4.png` | White wordmark in the offline preview masthead | `ad13823385f33c4d1fe9b2c04deea8ec1f33b5396c9fa676f48ee5c3bc4c25c2` |
| `YT_Banner_Tokn.jpg` | Paid briefs and free sample banner | `12455d7d216c8213e5ae1bf02f602318a71542f846158ba2bebd5dc816b65183` |

These files are committed as regular binary files here, so deployment and offline previews do not need Git LFS. Production uses the original source repository's commit-pinned public media URLs in `branding.py`. Discord retrieves them independently; no webhook token or market data is included in those URLs. Do not change URLs to a mutable branch or add arbitrary configurable image endpoints.

The HTML preview embeds each asset once as a data URL. Production delivery stays a single JSON webhook call; no image renderer, binary upload, package dependency, new host or paid model is required. Actual Discord clients choose their own image sizing and theme. If the source repository becomes private or the public media host is unavailable, images may not display; the card's text carries all market information.
