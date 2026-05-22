from dataclasses import dataclass, field
from typing import Dict, List

from sklearn.pipeline import Pipeline


@dataclass
class ForecastBundle:
    features: List[str]
    targets: List[str]
    model: Pipeline
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SetpointBundle:
    features: List[str]
    model: Pipeline
    metrics: Dict[str, float] = field(default_factory=dict)
