"""Species perception profiles used by animal entities."""

from sim.perception.profiles.base import PerceptionProfile

CAT = PerceptionProfile(species="cat", vision_radius=8.0, hearing_radius=18.0)
DOG = PerceptionProfile(species="dog", vision_radius=9.0, hearing_radius=22.0)
RAVEN = PerceptionProfile(species="raven", vision_radius=20.0, hearing_radius=12.0)
