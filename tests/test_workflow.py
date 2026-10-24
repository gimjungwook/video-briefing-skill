"""Small behavioural checks for the public outline and speed contracts."""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import make_audio
import motion_kit


class WorkflowTests(unittest.TestCase):
    def test_normal_speed_default_and_override_order(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,{},clear=True):
            root=Path(d)
            self.assertEqual(make_audio.tempo_of(root),1)
            os.environ["VB_TEMPO"]="2"
            self.assertEqual(make_audio.tempo_of(root),2)
            (root/"tempo.txt").write_text("1")
            self.assertEqual(make_audio.tempo_of(root),1)
            (root/"tempo.txt").write_text("nan")
            with self.assertRaises(SystemExit):
                make_audio.tempo_of(root)

    def test_demo_cues_cover_every_flow_and_card(self):
        meta,slides=motion_kit.read(ROOT/"examples/demo/outline.md")
        self.assertEqual(meta['theme'],'paper')
        self.assertEqual(len(slides),3)
        for slide in slides:
            regions={r for _,rs in slide['say'] for r in rs.split('+')}
            if slide['t']=='flow':
                self.assertTrue({'title','s0','s1','s2'}<=regions)
            if slide['t']=='cards':
                self.assertTrue({'title','c0','c1','c2'}<=regions)

    def test_korean_pronunciation_changes_speech_only(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            original=['AI 작업 결과를 알려 드려요.']
            (root/'narration.json').write_text(json.dumps(original))
            (root/'spoken.json').write_text(json.dumps([['AI','에이아이']]))
            spoken,problems=make_audio.spoken_text(root)
            self.assertEqual(spoken,['에이아이 작업 결과를 알려 드려요.'])
            self.assertFalse(problems)
            self.assertEqual(json.loads((root/'narration.json').read_text()),original)


if __name__=='__main__':
    unittest.main()
