"""CORE-02 (init), PROF-01..03 (sync + profile), PROF-04 (confirm)."""

import json
import stat
import subprocess

import pytest
from conftest import FIXTURES, FakeAdapter, _base_env, competition_fixture, kx

from kx.credentials import detect_source, mask, permission_warnings
from kx.profile import build_profile

TOKEN = "KGAT_" + "f" * 28 + "9z9z"


def test_init_validates_and_masks(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    env = kx(ws, fake, "init", "titanic")
    assert env["status"] == "ok"
    assert env["data"]["username"] == "tester"
    blob = json.dumps(env)
    assert TOKEN not in blob and "f" * 20 not in blob
    assert env["data"]["credential"]["masked"].endswith("9z9z")
    assert env["next_action"]["command"] == "kx sync titanic"
    for rel in (".gitignore", ".githooks/pre-commit", "control/config.json", "control/state.json",
                "control/ledger.jsonl", "strategy.md", "README.md"):
        assert (ws / rel).exists(), rel
    assert not (ws / ".env").exists() and not (ws / ".claude").exists()
    state = json.loads((ws / "control/state.json").read_text())
    assert state["credentials"]["status"] == "VALIDATED"
    assert TOKEN not in (ws / "control/state.json").read_text()
    log = subprocess.run(["git", "log", "--oneline"], cwd=ws, capture_output=True, text=True,
                         env=_base_env())
    assert "scaffold" in log.stdout
    hooks = subprocess.run(["git", "config", "core.hooksPath"], cwd=ws, capture_output=True,
                           text=True, env=_base_env())
    assert hooks.stdout.strip() == ".githooks"


def test_init_is_idempotent_and_never_overwrites(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    kx(ws, fake, "init")
    (ws / "README.md").write_text("mine")
    env = kx(ws, fake, "init")
    assert env["status"] == "ok" and env["data"]["created"] == []
    assert (ws / "README.md").read_text() == "mine"


def test_init_rejected_credential_needs_user(tmp_path, token_home):
    fake = FakeAdapter()
    fake.valid = False
    env = kx(tmp_path / "ws", fake, "init")
    assert env["status"] == "needs_user" and env["errors"] == ["credential_invalid"]


def test_init_refuses_a_v1_workspace(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    (ws / "control").mkdir(parents=True)
    (ws / "control/config.json").write_text(json.dumps({"workspace_version": 1}))
    env = kx(ws, fake, "init")
    assert env["status"] == "invalid" and env["errors"] == ["workspace_version_mismatch"]


def test_mask_and_permission_warning(token_home):
    assert mask("abcd") == "****"
    assert mask("KGAT_1234567890", 5) == "KGAT_******7890"
    src = detect_source()
    assert src["type"] == "scoped API token" and TOKEN not in json.dumps(src)
    tok = token_home / ".kaggle" / "access_token"
    tok.chmod(0o644)
    warns = permission_warnings()
    assert warns and "chmod 600" in warns[0]
    tok.chmod(stat.S_IRUSR | stat.S_IWUSR)
    assert permission_warnings() == []


def test_sync_writes_structured_profile_only(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "titanic")
    env = kx(ws, fake, "sync")
    assert env["status"] == "ok"
    prof = json.loads((ws / "control/profile.json").read_text())
    assert prof["canonical_ref"] == "titanic"
    assert prof["competition"]["evaluation_metric"] == "Categorization Accuracy"
    assert prof["competition"]["max_daily_submissions"] == 10
    assert prof["competition"]["is_kernels_submissions_only"] is False
    assert prof["files_summary"]["total_file_count"] == 3
    assert {f["name"] for f in prof["root_listing"]["files"]} == \
        {"gender_submission.csv", "test.csv", "train.csv"}
    text = json.dumps(prof)
    assert "description" not in text and "https://" not in text
    assert prof["derived"]["metric_suggestion"] == "accuracy"
    assert env["next_action"]["kind"] == "ask_user"


def test_canonical_ref_keeps_case():
    raw = competition_fixture("equity-post-hct-survival-predictions")
    prof = build_profile("equity-post-hct-survival-predictions", raw["competition"],
                         raw["files_summary"], raw["tree_root"])
    assert prof["canonical_ref"] == "equity-post-HCT-survival-predictions"
    assert prof["slug"] == "equity-post-hct-survival-predictions"


# Hand-verified ground truth from spike 001 (mode, modality, api_served).
TRUTH = {
    "titanic": ("csv_upload", {"tabular"}, False),
    "playground-series-s6e2": ("csv_upload", {"tabular"}, False),
    "digit-recognizer": ("csv_upload", {"tabular", "image"}, False),
    "spaceship-titanic": ("csv_upload", {"tabular"}, False),
    "connectx": ("agent", {"none"}, False),
    "arc-prize-2026-arc-agi-2": ("code_kernel", {"structured"}, False),
    "rsna-knee-abnormality-detection": ("code_kernel", {"image"}, False),
    "orbit-wars": ("agent", {"none"}, False),
    "gemma-4-good-hackathon": ("writeup", {"none"}, False),
    "kaggle-measuring-agi": ("writeup", {"none"}, False),
    "pokemon-tcg-ai-battle-challenge-strategy": ("writeup", {"none"}, False),
    "equity-post-hct-survival-predictions": ("code_kernel", {"tabular"}, False),
    "jane-street-real-time-market-data-forecasting": ("code_kernel", {"tabular"}, True),
    "isic-2024-challenge": ("code_kernel", {"image"}, False),
    "llm-prompt-recovery": ("code_kernel", {"text"}, False),
    "birdclef-2025": ("code_kernel", {"audio"}, False),
    "m5-forecasting-accuracy": ("csv_upload", {"tabular"}, False),
    "cooked-or-not": ("csv_upload", {"image"}, False),
    "um-game-playing-strength-of-mcts-variants": ("code_kernel", {"tabular"}, True),
}


@pytest.mark.parametrize("slug", sorted(TRUTH))
def test_classifier_matches_ground_truth(slug):
    raw = competition_fixture(slug)
    prof = build_profile(slug, raw["competition"], raw["files_summary"], raw["tree_root"],
                         raw.get("tree_depth1") or None)
    mode, modalities, api = TRUTH[slug]
    d = prof["derived"]
    assert d["submission_mode"] == mode
    assert d["modality"] in modalities
    assert d["api_served"] is api
    assert d["reasons"]


def test_nemotron_is_the_unknown_residual():
    raw = competition_fixture("nvidia-nemotron-model-reasoning-challenge")
    prof = build_profile("nvidia-nemotron-model-reasoning-challenge", raw["competition"],
                         raw["files_summary"], raw["tree_root"])
    assert prof["derived"]["submission_mode"] == "unknown"


def test_expected_output_and_late_submissions():
    raw = competition_fixture("um-game-playing-strength-of-mcts-variants")
    d = build_profile("um-game-playing-strength-of-mcts-variants", raw["competition"],
                      raw["files_summary"], raw["tree_root"])["derived"]
    assert d["expected_output"] == "submission.parquet"
    assert d["closed"] is True and d["late_submissions_open"] is True
    raw = competition_fixture("arc-prize-2026-arc-agi-2")
    d = build_profile("arc-prize-2026-arc-agi-2", raw["competition"], raw["files_summary"],
                      raw["tree_root"])["derived"]
    assert d["expected_output"] == "submission.json"


def test_confirm_requires_note_and_a_known_mode(tmp_path, token_home):
    fake = FakeAdapter(comp_slug="nvidia-nemotron-model-reasoning-challenge")
    ws = tmp_path / "ws"
    kx(ws, fake, "init", "nvidia-nemotron-model-reasoning-challenge")
    kx(ws, fake, "sync")
    env = kx(ws, fake, "confirm", "--note", "x")
    assert env["status"] == "invalid" and env["errors"] == ["mode_unknown"]
    assert kx(ws, fake, "confirm", "--mode", "artifact_upload")["errors"] == ["note_required"]
    env = kx(ws, fake, "confirm", "--mode", "artifact_upload", "--note", "Evaluation page: LoRA")
    assert env["status"] == "ok" and env["data"]["template"] == "custom"
    assert env["data"]["type_guides"] == ["references/types/custom.md"]
    prof = json.loads((ws / "control/profile.json").read_text())
    assert prof["confirmed"]["overrides"] == {"submission_mode": "artifact_upload"}
    env = kx(ws, fake, "new", "--idea", "x", "--hypothesis", "y")
    assert env["status"] == "invalid" and env["errors"] == ["metric_unset"]  # unknown metric
    assert kx(ws, fake, "submit", "exp-001")["errors"] == ["no_submission_path"]


def test_resync_keeps_confirmation_when_facts_unchanged(ready_ws, fake):
    kx(ready_ws, fake, "sync")
    prof = json.loads((ready_ws / "control/profile.json").read_text())
    assert prof["confirmed"]


def test_status_walks_the_loop(tmp_path, token_home, fake):
    ws = tmp_path / "ws"
    assert kx(ws, fake, "status")["next_action"]["command"] == "kx init"
    kx(ws, fake, "init", "titanic")
    assert kx(ws, fake, "status")["next_action"]["command"] == "kx sync titanic"
    kx(ws, fake, "sync")
    assert kx(ws, fake, "status")["next_action"]["kind"] == "ask_user"
    kx(ws, fake, "confirm", "--note", "ok")
    assert kx(ws, fake, "status")["next_action"]["command"] == "kx metric accuracy"
    kx(ws, fake, "metric", "accuracy")
    env = kx(ws, fake, "status")
    assert env["next_action"]["command"] == "kx diagnose"  # validation unchecked
    assert env["data"]["validation"] == "unchecked"


def test_fixture_competitions_carry_no_prose():
    for f in (FIXTURES / "competitions").glob("*.json"):
        assert '"description"' not in f.read_text(), f.name
