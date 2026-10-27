import unittest
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln import rate_content, rate_notes
from rcln.engine import _tap, _rc_aggregate
from spm_rating import rate_notes as upstream, load_model
from spm_rating import engine


def chart(keys, kind):
    lines = ['osu file format v14', '[General]', 'Mode:3', '[Difficulty]',
             f'CircleSize:{keys}', 'OverallDifficulty:7', '[HitObjects]']
    for i in range(60):
        x = int((i % keys + .5)*512/keys); t = 1000+150*i
        ln = kind == 'ln' or (kind == 'mixed' and i % 5 == 0)
        lines.append(f'{x},192,{t},128,0,{t+370}:0:0:0:0:' if ln else f'{x},192,{t},1,0,0:0:0:0:')
    return '\n'.join(lines)


class Scores(unittest.TestCase):
    def test_upstream_and_supported_modes(self):
        for model in ('detail', 'compact'):
            for keys in (4, 6, 7):
                for kind in ('tap', 'ln', 'mixed'):
                    with self.subTest(model=model, keys=keys, kind=kind):
                        notes = engine.parser.parse_content(chart(keys, kind), rate=1.25)
                        got = rate_notes(notes, model)
                        self.assertNotIn('rc_head_only', got)
                        self.assertAlmostEqual(got['spm'], upstream(notes, model)['score'], places=10)
                        if kind == 'tap': self.assertEqual(got['rc'], got['spm'])
                        if kind == 'ln':
                            tap = replace(notes, is_ln=np.zeros(notes.n_notes, bool), ln_end=notes.time.copy())
                            self.assertLess(abs(got['rc']-upstream(tap, model)['score']), .005)
                        mirror = rate_notes(engine.mirror(notes), model)
                        for key in ('spm', 'rc', 'ln', 'ln_coverage'):
                            self.assertAlmostEqual(got[key], mirror[key], places=9)
                        if kind == 'tap':
                            self.assertEqual(got['ln_coverage'], 0.)
                            self.assertEqual(got['ln'], 0.)

    def test_fractional_time_and_scales(self):
        notes = engine.parser.parse_content(chart(7, 'mixed'))
        shift = np.where(notes.col % 2, .35, .7)
        notes = replace(notes, time=notes.time+shift, ln_end=np.where(notes.is_ln, notes.ln_end+shift, notes.ln_end))
        got = rate_notes(notes, scale='reference')
        self.assertAlmostEqual(got['spm'], upstream(notes, 'detail', scale='reference')['score'], places=9)
        raw = rate_notes(notes); cal = load_model('detail').alignment['7']
        self.assertAlmostEqual(got['ln'], cal['scale']*raw['ln']**cal['power'], places=10)
        self.assertAlmostEqual(got['rc'], cal['scale']*raw['rc']**cal['power'], places=10)

    def test_input_and_cancel(self):
        with self.assertRaises(ValueError): rate_content(chart(5, 'tap'))
        with self.assertRaises(ValueError): rate_content(chart(7, 'tap'), rate=0)
        with self.assertRaises(InterruptedError): rate_content(chart(7, 'tap'), cancel=lambda: True)

    def test_local_ln_difficulty_changes_rc_weights(self):
        notes = engine.parser.parse_content(chart(7, 'mixed'))
        e = engine.get(); p = dict(load_model('detail').parameters)
        full = e.build(notes, p); rice = e.build(_tap(notes), p)
        g = (full.t >= 5500).astype(float)
        rc = np.where(g == 0, 10., 5.)
        weak_ln = np.where(g == 0, 2., 1.)
        strong_ln = np.where(g == 0, 2., 20.)
        low = _rc_aggregate(full, rice, weak_ln, rc, g, 1., 1., p)[0]
        high = _rc_aggregate(full, rice, strong_ln, rc, g, 1., 1., p)[0]
        self.assertGreater(high, low)

if __name__ == '__main__': unittest.main()
