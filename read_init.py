import youtube_transcript_api
import os

init_path = youtube_transcript_api.__file__
print(f"Reading: {init_path}")
try:
    with open(init_path, 'r') as f:
        print(f.read())
except Exception as e:
    print(e)
