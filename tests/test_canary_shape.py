import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import canary_shape as cs  # noqa: E402

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _act(body: str) -> str:
    return f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body></act></akomaNtoso>'


FLAT = (
    '<section eId="sec-1"><p>one</p></section>'
    '<hcontainer name="clause" eId="cl-1"><p>two words</p></hcontainer>'
)


def _corpus(tmp_path, bodies: dict[str, str], **index_extra) -> Path:
    (tmp_path / "xml").mkdir(parents=True)
    acts = {}
    for slug, body in bodies.items():
        (tmp_path / "xml" / f"{slug}.xml").write_text(_act(body))
        acts[slug] = {"name": slug, "xml_path": f"xml/{slug}.xml"}
    (tmp_path / "index.json").write_text(json.dumps({"acts": acts, **index_extra}))
    return tmp_path


def test_sample_is_deterministic_and_bounded():
    index = {"acts": {f"a{i}": {} for i in range(50)}}
    assert cs.sample_acts(index, 10) == cs.sample_acts(index, 10)
    assert len(cs.sample_acts(index, 10)) == 10


def test_matching_baseline_is_clean(tmp_path):
    base = cs.measure(_corpus(tmp_path, {"a": FLAT}, structure_version=2), 200)
    hard, warn = cs.compare(base, base, 0.10)
    assert hard == [] and warn == []


def test_new_hcontainer_name_is_a_hard_failure(tmp_path):
    base = cs.measure(_corpus(tmp_path / "b", {"a": FLAT}, structure_version=2), 200)
    changed = FLAT + '<hcontainer name="newshape" eId="x"><p>y</p></hcontainer>'
    now = cs.measure(_corpus(tmp_path / "n", {"a": changed}, structure_version=2), 200)
    hard, _ = cs.compare(now, base, 0.10)
    assert any("newshape" in h for h in hard)


def test_duplicate_and_empty_eids_are_hard_failures(tmp_path):
    base = cs.measure(_corpus(tmp_path, {"a": FLAT}, structure_version=2), 200)
    bad = dict(base, duplicate_eids=1, empty_eids=1)
    hard, _ = cs.compare(bad, base, 0.10)
    assert len(hard) == 2


def test_unknown_version_is_a_hard_failure_and_absent_is_a_warning(tmp_path):
    base = cs.measure(_corpus(tmp_path, {"a": FLAT}, structure_version=2), 200)
    hard, _ = cs.compare(dict(base, structure_version=3), base, 0.10)
    assert any("structure_version 3" in h for h in hard)
    hard, warn = cs.compare(dict(base, structure_version=None), base, 0.10)
    assert hard == [] and any("no structure_version" in w for w in warn)


def test_count_drift_beyond_tolerance_warns_but_does_not_fail(tmp_path):
    base = cs.measure(_corpus(tmp_path, {"a": FLAT}, structure_version=2), 200)
    drifted = json.loads(json.dumps(base))
    drifted["words"]["attachment"] = base["words"]["attachment"] + 100
    drifted["tags"]["section"] = base["tags"]["section"] * 3
    hard, warn = cs.compare(drifted, base, 0.10)
    assert hard == [] and any("tags[section]" in w for w in warn)


def test_attachment_words_are_measured(tmp_path):
    body = '<hcontainer name="clause" eId="c"><p>x</p></hcontainer>'
    att = f'<attachments xmlns="{NS}"><attachment><doc><mainBody><p>one two three</p></mainBody></doc></attachment></attachments>'
    root = tmp_path / "xml"
    root.mkdir()
    (root / "a.xml").write_text(
        f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body>{att}</act></akomaNtoso>'
    )
    assert cs.measure_act(root / "a.xml")["words"]["attachment"] == 3
