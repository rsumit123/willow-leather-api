"""
DNA dataclasses for Match Engine v2.
BatterDNA, PacerDNA, SpinnerDNA, PitchDNA with serialization support.
"""
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Union


def clamp(val, lo=0, hi=100):
    return max(lo, min(hi, val))


@dataclass
class BatterDNA:
    vs_pace: int = 50
    vs_bounce: int = 50
    vs_spin: int = 50
    vs_deception: int = 50
    off_side: int = 50
    leg_side: int = 50
    power: int = 50
    weaknesses: List[str] = field(default_factory=list)

    def avg(self):
        return (self.vs_pace + self.vs_bounce + self.vs_spin + self.vs_deception
                + self.off_side + self.leg_side) / 6

    def to_dict(self) -> dict:
        return {
            "vs_pace": self.vs_pace,
            "vs_bounce": self.vs_bounce,
            "vs_spin": self.vs_spin,
            "vs_deception": self.vs_deception,
            "off_side": self.off_side,
            "leg_side": self.leg_side,
            "power": self.power,
            "weaknesses": self.weaknesses,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BatterDNA":
        return cls(
            vs_pace=d.get("vs_pace", 50),
            vs_bounce=d.get("vs_bounce", 50),
            vs_spin=d.get("vs_spin", 50),
            vs_deception=d.get("vs_deception", 50),
            off_side=d.get("off_side", 50),
            leg_side=d.get("leg_side", 50),
            power=d.get("power", 50),
            weaknesses=d.get("weaknesses", []),
        )


@dataclass
class PacerDNA:
    speed: int = 135      # kph, 120-155
    swing: int = 50
    bounce: int = 50
    control: int = 60

    def avg(self):
        return (self.speed_factor() + self.swing + self.bounce + self.control) / 4

    def speed_factor(self):
        """Normalize speed to 0-100 scale for calculations."""
        return max(0, min(100, (self.speed - 115) * 2.5))

    def to_dict(self) -> dict:
        return {
            "type": "pacer",
            "speed": self.speed,
            "swing": self.swing,
            "bounce": self.bounce,
            "control": self.control,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PacerDNA":
        return cls(
            speed=d.get("speed", 135),
            swing=d.get("swing", 50),
            bounce=d.get("bounce", 50),
            control=d.get("control", 60),
        )


@dataclass
class SpinnerDNA:
    turn: int = 50
    flight: int = 50
    variation: int = 50
    control: int = 60

    def avg(self):
        return (self.turn + self.flight + self.variation + self.control) / 4

    def to_dict(self) -> dict:
        return {
            "type": "spinner",
            "turn": self.turn,
            "flight": self.flight,
            "variation": self.variation,
            "control": self.control,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpinnerDNA":
        return cls(
            turn=d.get("turn", 50),
            flight=d.get("flight", 50),
            variation=d.get("variation", 50),
            control=d.get("control", 60),
        )


def bowler_dna_from_dict(d: dict) -> Union[PacerDNA, SpinnerDNA]:
    """Deserialize bowler DNA from dict, auto-detecting type."""
    if d.get("type") == "spinner":
        return SpinnerDNA.from_dict(d)
    return PacerDNA.from_dict(d)


@dataclass
class PitchDNA:
    name: str = "balanced"
    pace_assist: int = 55
    spin_assist: int = 45
    bounce: int = 60
    carry: int = 65
    deterioration: int = 35


# Pitch presets
PITCHES = {
    "green_seamer": PitchDNA("green_seamer", pace_assist=80, spin_assist=15, bounce=70, carry=85, deterioration=25),
    "dust_bowl":    PitchDNA("dust_bowl",    pace_assist=20, spin_assist=85, bounce=35, carry=45, deterioration=80),
    "flat_deck":    PitchDNA("flat_deck",    pace_assist=40, spin_assist=35, bounce=55, carry=60, deterioration=20),
    "bouncy_track": PitchDNA("bouncy_track", pace_assist=75, spin_assist=20, bounce=90, carry=85, deterioration=20),
    "slow_turner":  PitchDNA("slow_turner",  pace_assist=30, spin_assist=60, bounce=40, carry=50, deterioration=55),
    "balanced":     PitchDNA("balanced",     pace_assist=55, spin_assist=45, bounce=60, carry=65, deterioration=35),
}
