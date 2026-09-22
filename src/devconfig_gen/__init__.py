"""Provider-based developer configuration generation.

The package exposes the provider pipeline and the stable CLI/Python API only.
Importing it has no side effects.
"""

from .engine import (
    build_request,
    describe_provider,
    diagnose_request,
    generate,
    generate_from_file,
    generate_pipeline,
    validate_request,
)
from .formats import (
    FormatError,
    coerce_scalar,
    deep_merge,
    dump_data,
    dump_file,
    dumps,
    load_data,
    load_file,
    loads,
)
from .models import (
    ConfigProvider,
    Diagnostic,
    GeneratedArtifact,
    GenerationRequest,
    GenerationResult,
    ProviderField,
    ProviderStep,
    WebUIWidgets,
)
from .registry import ProviderRegistry, default_registry
from .validation import ValidationError

__all__ = [
    "ConfigProvider",
    "Diagnostic",
    "FormatError",
    "GeneratedArtifact",
    "GenerationRequest",
    "GenerationResult",
    "ProviderField",
    "ProviderRegistry",
    "ProviderStep",
    "ValidationError",
    "WebUIWidgets",
    "build_request",
    "coerce_scalar",
    "deep_merge",
    "default_registry",
    "describe_provider",
    "diagnose_request",
    "dump_data",
    "dump_file",
    "dumps",
    "generate",
    "generate_from_file",
    "generate_pipeline",
    "load_data",
    "load_file",
    "loads",
    "validate_request",
]
__version__ = "2.1.5"
