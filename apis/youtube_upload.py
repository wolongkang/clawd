import logging
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# Paths — client secret in project root, token in data dir
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_SECRET_FILE = os.path.join(PROJECT_DIR, "client_secret.json")
TOKEN_DIR = os.path.join(PROJECT_DIR, "data")
TOKEN_FILE = os.path.join(TOKEN_DIR, "youtube_token.json")


def is_available() -> bool:
    """Check if YouTube upload is configured (has valid token)."""
    return os.path.exists(TOKEN_FILE)


def _get_credentials() -> Credentials:
    """Load or refresh YouTube API credentials."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            logger.info("YouTube token refreshed successfully")
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return None

    if not creds or not creds.valid:
        logger.error("No valid YouTube credentials. Run youtube_auth.py first.")
        return None

    return creds


def _save_token(creds: Credentials):
    """Save credentials to token file."""
    os.makedirs(TOKEN_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    logger.info(f"Token saved to {TOKEN_FILE}")


def authenticate_interactive():
    """
    Run interactive OAuth flow (opens browser).
    Call this ONCE from youtube_auth.py to get initial refresh token.
    """
    if not os.path.exists(CLIENT_SECRET_FILE):
        logger.error(f"Client secret not found: {CLIENT_SECRET_FILE}")
        return False

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent")
    _save_token(creds)
    logger.info("YouTube authentication successful!")
    return True


async def upload_video(
    file_path: str,
    title: str,
    description: str = "",
    tags: list[str] = None,
    category_id: str = "22",  # 22 = People & Blogs
    privacy: str = "private",  # private, unlisted, or public
) -> dict:
    """
    Upload a video to YouTube.

    Returns dict with:
      - video_id: YouTube video ID
      - url: Full YouTube URL
    Or None on failure.
    """
    creds = _get_credentials()
    if not creds:
        logger.error("Cannot upload: no valid YouTube credentials")
        return None

    if not os.path.exists(file_path):
        logger.error(f"Video file not found: {file_path}")
        return None

    try:
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],  # YouTube max title is 100 chars
                "description": description[:5000],  # Max 5000 chars
                "tags": (tags or [])[:500],
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        logger.info(f"Uploading to YouTube: {title} ({size_mb:.1f}MB, {privacy})")

        media = MediaFileUpload(
            file_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=10 * 1024 * 1024,  # 10MB chunks
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        # Execute upload with progress logging
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                logger.info(f"Upload progress: {progress}%")

        video_id = response["id"]
        url = f"https://youtu.be/{video_id}"
        logger.info(f"Upload complete! {url}")

        return {
            "video_id": video_id,
            "url": url,
            "title": title,
            "privacy": privacy,
        }

    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        return None
