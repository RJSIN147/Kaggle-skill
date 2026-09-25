"""Build b-notebook/predict.ipynb from a-script/predict.py (one code cell, python3 kernelspec)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
src = (HERE / "a-script" / "predict.py").read_text().replace("Spike 003a: a SCRIPT kernel", "Spike 003b: a NOTEBOOK kernel")
nb = {
    "cells": [{"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src.splitlines(keepends=True)}],
    "metadata": {
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
out = HERE / "b-notebook"
out.mkdir(exist_ok=True)
(out / "predict.ipynb").write_text(json.dumps(nb, indent=1) + "\n")
meta = json.loads((HERE / "a-script" / "kernel-metadata.json").read_text())
meta.update(id="ravijotsinha/kx-spike-003-notebook", title="kx-spike-003-notebook",
            code_file="predict.ipynb", kernel_type="notebook")
(out / "kernel-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
print("wrote", out)
