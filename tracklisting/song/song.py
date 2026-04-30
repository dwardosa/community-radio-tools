from dataclasses import dataclass, field


@dataclass
class Song:
    title: str
    artist: str
    show_name: str = field(default="")
    identified_at: str = field(default="")
    shazam_url: str = field(default=None)
    thumbnail_url: str = field(default=None)

    @property
    def full_title(self) -> str:
        return f"{self.title} - {self.artist}"
