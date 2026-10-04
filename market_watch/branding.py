"""Fixed public Tokn assets; no remote lookups or configurable image destinations."""

SOURCE_REPOSITORY = 'ToknNews/ToknNews-Full_Backup'
SOURCE_REVISION = '70fcd4b37147acbb34294b5086d597d7d04bf2ce'
ASSET_BASE = ('https://media.githubusercontent.com/media/' + SOURCE_REPOSITORY + '/'
              + SOURCE_REVISION + '/frontend/assets/img/')
ICON_URL = ASSET_BASE + 'Tokn_Favicon.png'
BANNER_URL = ASSET_BASE + 'YT_Banner_Tokn.jpg'
WEBHOOK_NAME = 'Tokn Market Watch'
TOKN_BLUE = 0x2D73FF  # rgba(45, 115, 255, ...) in the existing Tokn global CSS.
ASSET_HASHES = {
    'Tokn_Favicon.png': 'a4ea8c2083f56dd55a00c0e08e6233679ed7a0c271931c5f0bf4db0205231adb',
    'Tokn_Logo_Main_4.png': 'ad13823385f33c4d1fe9b2c04deea8ec1f33b5396c9fa676f48ee5c3bc4c25c2',
    'YT_Banner_Tokn.jpg': '12455d7d216c8213e5ae1bf02f602318a71542f846158ba2bebd5dc816b65183',
}
