try:
    from youtube_transcript_api._api import YouTubeTranscriptApi
    print(f"Direct Import Type: {type(YouTubeTranscriptApi)}")
    print(f"Has get_transcript: {hasattr(YouTubeTranscriptApi, 'get_transcript')}")
    print(f"Dir: {dir(YouTubeTranscriptApi)}")
except Exception as e:
    print(f"Error: {e}")
