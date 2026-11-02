import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
spec=importlib.util.spec_from_file_location('publication',TOOLS/'publish_full_export.py')
pub=importlib.util.module_from_spec(spec);spec.loader.exec_module(pub)


def setup(tmp_path,monkeypatch,text):
    root=tmp_path/'target';source=tmp_path/'source';root.mkdir();source.mkdir()
    (root/'docs/migration').mkdir(parents=True)
    (root/'docs/migration/operations-lineage.json').write_text('{"checks":[]}')
    (source/'s.py').write_bytes(b'def example():\n    pass \n\n')
    (root/'a.py').write_bytes((source/'s.py').read_bytes())
    monkeypatch.setattr(pub,'ROOT',root)
    monkeypatch.setattr(pub.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=2,stdout=text,stderr=''))
    return source,dict(files=[dict(path='s.py',sha256=pub.sha(source/'s.py'))]),dict(files=[dict(source='s.py',target='a.py')])


def test_only_exact_retained_source_whitespace_is_accepted(tmp_path,monkeypatch):
    args=setup(tmp_path,monkeypatch,'a.py:2: trailing whitespace.\n+    pass \na.py:3: new blank line at EOF.\n')
    assert len(pub.retained_whitespace(*args))==2


@pytest.mark.parametrize('diagnostic',['a.py:2: space before tab in indent.\n','new.py:2: trailing whitespace.\n','unparsed error\n'])
def test_unknown_new_or_unparsed_whitespace_cannot_publish(tmp_path,monkeypatch,diagnostic):
    args=setup(tmp_path,monkeypatch,diagnostic)
    with pytest.raises(AssertionError):pub.retained_whitespace(*args)
