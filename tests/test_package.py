from importlib.metadata import version


def test_package_metadata_and_import():
    import pylingual_web_batch

    assert pylingual_web_batch.__version__ == version("pylingual-web-batch")
