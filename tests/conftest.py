"""Keep every test off this machine's real command folder.

`ybase setup` writes a launcher into YB_BIN_DIR (default: ~/.local/bin). Many tests run
setup with the real HOME, so the whole run is pointed at a throwaway folder instead.
"""
import os
import tempfile

os.environ["YB_BIN_DIR"] = tempfile.mkdtemp(prefix="ybase-test-bin-")
