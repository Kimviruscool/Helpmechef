from youtube_transcript_api import YouTubeTranscriptApi
print(dir(YouTubeTranscriptApi))
try:
    print(YouTubeTranscriptApi.get_transcript("dQw4w9WgXcQ"))
except Exception as e:
    print(e)
