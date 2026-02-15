import sys
import os

print("--- SYS.PATH ---")
for p in sys.path:
    print(p)

try:
    import youtube_transcript_api
    print("\n--- MODULE ---")
    print(f"File: {youtube_transcript_api.__file__}")
    print(f"Dir: {dir(youtube_transcript_api)}")
    
    from youtube_transcript_api import YouTubeTranscriptApi
    print("\n--- CLASS ---")
    print(f"Type: {type(YouTubeTranscriptApi)}")
    print(f"Dir: {dir(YouTubeTranscriptApi)}")
    
    if hasattr(YouTubeTranscriptApi, 'get_transcript'):
        print("get_transcript found!")
    else:
        print("get_transcript NOT found!")
        
except ImportError as e:
    print(f"ImportError: {e}")
except Exception as e:
    print(f"Error: {e}")
