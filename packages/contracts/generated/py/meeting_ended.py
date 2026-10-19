"""
Auto-generated from packages/contracts/meeting_ended.schema.json
DO NOT EDIT DIRECTLY. Run `python packages/contracts/scripts/generate_contracts.py` to regenerate.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class Participant(BaseModel):
    clerk_user_id: str = Field(..., description="Unique Clerk user ID")
    display_name: str = Field(..., description="Display name of participant")
    email: str = Field(..., description="Email address")


class TranscriptSegment(BaseModel):
    speaker: str = Field(..., description="Speaker label (e.g. SPEAKER_01)")
    speaker_user_id: Optional[str] = Field(default=None, description="Mapped Clerk user ID if resolved")
    start: float = Field(..., description="Start timestamp in seconds")
    end: float = Field(..., description="End timestamp in seconds")
    text: str = Field(..., description="Transcribed text")


class MeetingEndedPayload(BaseModel):
    meeting_id: str = Field(..., description="Unique meeting UUID")
    org_id: str = Field(..., description="Clerk organization ID")
    title: str = Field(..., description="Meeting title")
    started_at: str = Field(..., description="ISO-8601 start timestamp")
    ended_at: str = Field(..., description="ISO-8601 end timestamp")
    language: str = Field(default="en", description="Transcript language")
    participants: List[Participant] = Field(default_factory=list, description="Participant attendees")
    transcript: List[TranscriptSegment] = Field(..., description="Attributed transcript segments")
    summary: Optional[str] = Field(default=None, description="Meeting summary")
    recording_url: Optional[str] = Field(default=None, description="Cloudinary/Stream recording URL")
