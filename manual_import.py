import youtube_transcript_api
try:
    print(youtube_transcript_api.YouTubeTranscriptApi.get_transcript("dQw4w9WgXcQ"))
    print("SUCCESS")
except Exception as e:
    print(f"ERROR: {e}")

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    print(YouTubeTranscriptApi.get_transcript("dQw4w9WgXcQ"))
    print("SUCCESS 2")
except Exception as e:
    print(f"ERROR 2: {e}")
