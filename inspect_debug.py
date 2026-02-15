from youtube_transcript_api import YouTubeTranscriptApi
import inspect

print(f"Type: {type(YouTubeTranscriptApi)}")
print(f"Source file: {inspect.getsourcefile(YouTubeTranscriptApi)}")
try:
    print(f"Source:\n{inspect.getsource(YouTubeTranscriptApi)[:500]}")
except:
    print("Could not get source")

print("\nDirect attributes:")
print(dir(YouTubeTranscriptApi))
