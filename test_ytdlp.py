from yt_dlp import YoutubeDL

url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
ydl_opts = {
    'writesubtitles': True,
    'writeautomaticsub': True,
    'skip_download': True,
    'subtitleslangs': ['ko', 'en'],
    'quiet': True,
    'no_warnings': True,
}

try:
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        subtitles = info.get('subtitles', {})
        automatic_captions = info.get('automatic_captions', {})
        
        print("Manual Subtitles:", list(subtitles.keys()))
        print("Auto Captions:", list(automatic_captions.keys()))
        
        # Get URL for Korean
        ko_sub = subtitles.get('ko') or automatic_captions.get('ko')
        if ko_sub:
             print("Korean URL:", ko_sub[-1]['url'][:50] + "...")
        else:
             print("No Korean subtitles found.")
             
except Exception as e:
    print(f"Error: {e}")
