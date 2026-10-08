"""Recipe intent only. Values are not undocumented firmware/PTP enum codes."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


FujiFilm = Literal["provia", "velvia", "astia", "classic_chrome", "classic_negative", "pro_neg_std", "pro_neg_hi", "eterna", "eterna_bleach", "nostalgic_negative", "reala_ace", "acros", "monochrome", "sepia"]


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[2] = 2
    name: str = Field(default="PROVIA / Standard", min_length=1, max_length=120)
    target_model: Literal["X-T4", "X100VI"] = "X-T4"
    firmware_version: str = "2.12"
    film: FujiFilm = "provia"
    exposure: float = Field(default=0, ge=-3, le=3)
    wb: Literal["camera", "auto", "daylight", "shade", "tungsten", "kelvin"] = "camera"
    kelvin: int = Field(default=5500, ge=2500, le=10000)
    wb_red: int = Field(default=0, ge=-9, le=9)
    wb_blue: int = Field(default=0, ge=-9, le=9)
    dynamic_range: Literal[100, 200, 400] = 100
    highlights: int = Field(default=0, ge=-100, le=100)
    whites: int = Field(default=0, ge=-100, le=100)
    shadows: int = Field(default=0, ge=-100, le=100)
    blacks: int = Field(default=0, ge=-100, le=100)
    color: int = Field(default=0, ge=-4, le=4)
    sharpness: int = Field(default=0, ge=-4, le=4)
    clarity: int = Field(default=0, ge=-5, le=5)
    noise_reduction: int = Field(default=-4, ge=-4, le=4)
    grain: Literal["off", "weak", "strong"] = "off"
    grain_size: Literal["small", "large"] = "small"
    color_chrome: Literal["off", "weak", "strong"] = "off"
    fx_blue: Literal["off", "weak", "strong"] = "off"
    mono_filter: Literal["none", "yellow", "red", "green"] = "none"

    @model_validator(mode="before")
    @classmethod
    def migrate_fuji_tone_v1(cls, value):
        """Load saved v1 Fuji-style tone values into the four-way v2 model."""
        if not isinstance(value, dict) or value.get("version") != 1:
            return value
        migrated = dict(value)
        migrated["version"] = 2
        # Old Highlight Tone: negative softened highlights. Old Shadow Tone:
        # positive hardened shadows, the inverse of the photo-editor convention.
        migrated["highlights"] = round(float(migrated.get("highlights", 0)) * 25)
        migrated["shadows"] = round(float(migrated.get("shadows", 0)) * -25)
        migrated.setdefault("whites", 0)
        migrated.setdefault("blacks", 0)
        return migrated

    def unsupported(self) -> list[str]:
        if self.target_model == "X-T4" and self.film in {"reala_ace", "nostalgic_negative"}:
            return [f"{self.film} is absent from the reference X-T4 firmware."]
        return []
