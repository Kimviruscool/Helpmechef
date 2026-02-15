import youtube_transcript_api
print("Module dir:", dir(youtube_transcript_api))
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    print("Class dir:", dir(YouTubeTranscriptApi))
except ImportError:
    print("Class import failed")
