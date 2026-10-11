import hashlib
from importlib.resources import files

AXE_CORE = files("allymend").joinpath("_vendor", "axe-core")
AXE_SHA256 = "c24f097bd2f451d4f933e8bc7d8d539f8672a2ebcb5cc9f9f3eec8ca9470a0c1"


def test_vendored_axe_core_is_unmodified() -> None:
    source = AXE_CORE.joinpath("axe.min.js").read_bytes()
    assert source.startswith(b"/*! axe v4.13.0")
    assert hashlib.sha256(source).hexdigest() == AXE_SHA256


def test_axe_core_license_is_shipped() -> None:
    license_text = AXE_CORE.joinpath("LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("Mozilla Public License, version 2.0")
