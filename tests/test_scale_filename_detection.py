from biopic.imaging.scale_detection import infer_scale_metadata_from_filename


def test_infers_separate_microscope_camera_magnification_and_fluid() -> None:
    metadata = infer_scale_metadata_from_filename(
        "Leica-DM-2500_Canon_EOS 700 D3_40xoil.tif"
    )

    assert metadata["microscope"] == "Leica Microsystems DM2500"
    assert metadata["camera"] == "Canon EOS 700D"
    assert metadata["magnification"] == "40x"
    assert metadata["fluid"] == "Oil"


def test_no_fluid_token_defaults_to_air() -> None:
    metadata = infer_scale_metadata_from_filename("Zeiss_Axio_Observer_20x_scale.tif")

    assert metadata["microscope"] == "ZEISS Axio Observer"
    assert metadata["magnification"] == "20x"
    assert metadata["fluid"] == "Air"


def test_camera_catalogue_normalizes_known_camera_models() -> None:
    metadata = infer_scale_metadata_from_filename("scale_ZEISS_Axiocam_712_mono_20x.tif")

    assert metadata["camera"] == "ZEISS Axiocam 712 mono"


def test_camera_catalogue_handles_consumer_eos_models() -> None:
    metadata = infer_scale_metadata_from_filename("adapter_Canon_EOS_700D_10x.tif")

    assert metadata["camera"] == "Canon EOS 700D"
