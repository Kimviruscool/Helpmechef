import youtube_transcript_api
print(youtube_transcript_api.__file__)
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    print(type(YouTubeTranscriptApi))
    print(dir(YouTubeTranscriptApi))
except:
    pass
