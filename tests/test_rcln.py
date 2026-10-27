import unittest
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln import rate_content, rate_notes
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
    def test_upstream_and_head_only(self):
        for model in ('detail', 'compact'):
            for keys in (4, 6, 7):
                for kind in ('tap', 'ln', 'mixed'):
                    with self.subTest(model=model, keys=keys, kind=kind):
                        notes = engine.parser.parse_content(chart(keys, kind), rate=1.25)
                        tap = replace(notes, is_ln=np.zeros(notes.n_notes, bool), ln_end=notes.time.copy())
                        got = rate_notes(notes, model)
                        self.assertAlmostEqual(got['spm'], upstream(notes, model)['score'], places=10)
                        self.assertAlmostEqual(got['rc_head_only'], upstream(tap, model)['score'], places=10)
                        if kind == 'tap': self.assertEqual(got['rc'], got['spm'])
                        if kind == 'ln': self.assertLess(abs(got['rc']-got['rc_head_only']), .005)
                        mirror = rate_notes(engine.mirror(notes), model)
                        for key in ('spm', 'rc', 'rc_head_only', 'ln', 'ln_coverage'):
                            self.assertAlmostEqual(got[key], mirror[key], places=9)
                        if kind == 'tap':
                            self.assertEqual(got['ln_coverage'], 0.)
                            self.assertEqual(got['ln'], 0.)

    def test_fractional_time_and_scales(self):
        notes = engine.parser.parse_content(chart(7, 'mixed'))
        shift = np.where(notes.col % 2, .35, .7)
        notes = replace(notes, time=notes.time+shift, ln_end=np.where(notes.is_ln, notes.ln_end+shift, notes.ln_end))
        tap = replace(notes, is_ln=np.zeros(notes.n_notes, bool), ln_end=notes.time.copy())
        got = rate_notes(notes, scale='reference')
        self.assertAlmostEqual(got['spm'], upstream(notes, 'detail', scale='reference')['score'], places=9)
        self.assertAlmostEqual(got['rc_head_only'], upstream(tap, 'detail', scale='reference')['score'], places=9)
        raw = rate_notes(notes); cal = load_model('detail').alignment['7']
        self.assertAlmostEqual(got['ln'], cal['scale']*raw['ln']**cal['power'], places=10)

    def test_input_and_cancel(self):
        with self.assertRaises(ValueError): rate_content(chart(5, 'tap'))
        with self.assertRaises(ValueError): rate_content(chart(7, 'tap'), rate=0)
        with self.assertRaises(InterruptedError): rate_content(chart(7, 'tap'), cancel=lambda: True)

    def test_mixed_sections_favor_taps_and_remain_symmetric(self):
        def mixed(fast_is_ln):
            lines = ['osu file format v14', '[General]', 'Mode:3', '[Difficulty]',
                     'CircleSize:7', 'OverallDifficulty:7', '[HitObjects]']
            for section, step in enumerate((100, 300)):
                for i in range(100):
                    x = int((i % 7 + .5)*512/7); t = 1000+section*50000+step*i
                    ln = (section == 0) == fast_is_ln
                    lines.append(f'{x},192,{t},128,0,{t+250}:0:0:0:0:' if ln
                                 else f'{x},192,{t},1,0,0:0:0:0:')
            return '\n'.join(lines)
        fast_tap = rate_content(mixed(False))
        fast_ln = rate_content(mixed(True))
        self.assertGreater(fast_tap['rc'], fast_tap['rc_head_only'])
        self.assertLess(fast_ln['rc'], fast_ln['rc_head_only'])

if __name__ == '__main__': unittest.main()
