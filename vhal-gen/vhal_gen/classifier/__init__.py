"""Signal-to-VehicleProperty classification pipeline."""

from .signal_classifier import SignalClassifier
from .vendor_id_allocator import VendorIdAllocator

__all__ = [
    "SignalClassifier",
    "VendorIdAllocator",
]
